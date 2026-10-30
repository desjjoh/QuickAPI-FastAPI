import asyncio
from typing import Literal

import httpx
import pytest
from fastapi.routing import APIRoute

from app.config.application import create_app
from app.config.environment import settings
from app.config.metrics import REQUEST_COUNT

from .test_timeout_server import running

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('enabled', [False, True])
async def test_system_aliases_preserve_operational_exposure(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setattr(settings, 'DIAGNOSTICS_ENABLED', enabled)
    monkeypatch.setattr(settings, 'METRICS_ENABLED', enabled)
    app = create_app()
    routes = [route for route in app.routes if isinstance(route, APIRoute)]

    assert len([route for route in routes if route.path == '/']) == 1
    schema = app.openapi()

    assert '/' in schema['paths']
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url='http://test',
        follow_redirects=False,
    ) as client:
        for path, expected in [
            ('/', 200),
            ('/health', 200),
            ('/ready', 503),
            ('/info', 200 if enabled else 404),
            ('/system', 200 if enabled else 404),
            ('/metrics', 200 if enabled else 404),
        ]:
            spellings = (
                [path]
                if path == '/'
                else [path, path + '/', path.upper(), path.upper() + '/']
            )

            for spelling in spellings:
                response = await client.get(spelling)

                assert response.status_code == expected, (spelling, response.text)
                assert 'location' not in response.headers
                head = await client.head(spelling)

                assert head.status_code == expected and head.content == b''

            if path != '/':
                assert path + '/' not in schema['paths']


@pytest.mark.parametrize('enabled', [False, True])
async def test_framework_docs_and_schema_share_case_and_slash_matching(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
) -> None:
    monkeypatch.setattr(settings, 'DOCS_ENABLED', enabled)
    app = create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        for path in ['/DOCS/', '/REDOC', '/OPENAPI.JSON/', '/DOCS/oauth2-redirect']:
            for method in ['GET', 'HEAD']:
                response = await client.request(method, path)

                assert response.status_code == (200 if enabled else 404)
                assert 'location' not in response.headers
                if method == 'HEAD':
                    assert response.content == b''


async def test_alternate_spellings_keep_canonical_metric_labels() -> None:
    app = create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        assert (await client.get('/HEALTH/')).status_code == 200
        assert (await client.head('/Health')).status_code == 200

    samples = [
        sample
        for family in REQUEST_COUNT.collect()
        for sample in family.samples
        if sample.name == 'http_requests_total'
    ]

    assert {
        (s.labels['method'], s.labels['route'], s.labels['status']) for s in samples
    } == {
        ('GET', '/health', '200'),
        ('HEAD', '/health', '200'),
    }
    assert sum(s.value for s in samples) == 2


@pytest.mark.parametrize('protocol', ['h11', 'httptools'])
async def test_real_head_has_no_body_and_preserves_next_response(
    protocol: Literal['h11', 'httptools'],
) -> None:
    app = create_app()

    async with running(app, protocol) as port:
        reader, writer = await asyncio.open_connection('127.0.0.1', port)

        try:
            for path, status in [('/HEALTH/', 200), ('/missing', 404)]:
                writer.write(
                    f'HEAD {path} HTTP/1.1\r\nHost: localhost\r\n\r\n'.encode()
                )
                await writer.drain()
                headers = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 2)

                assert headers.startswith(f'HTTP/1.1 {status} '.encode())
                assert b'x-request-id:' in headers.lower()
                assert b'content-length:' in headers.lower()

            writer.write(
                b'GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'
            )
            await writer.drain()
            following = await asyncio.wait_for(reader.read(), 2)

            assert following.startswith(b'HTTP/1.1 200 ')
            assert b'"alive":true' in following
        finally:
            writer.close()
            await writer.wait_closed()
