from collections.abc import Mapping
from typing import cast
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI

from app.common.store.request_context import RequestContext
from app.config.application import create_app
from app.config.environment import settings

pytestmark = pytest.mark.integration


def test_configured_order_is_explicit() -> None:
    app: FastAPI = create_app()
    names: list[str] = [
        cast(type[object], middleware.cls).__name__
        for middleware in app.user_middleware
    ]

    assert names[:5] == [
        "RequestAdmission",
        "RequestCleanupASGIMiddleware",
        "TrustedProxyASGIMiddleware",
        "RequestContextASGIMiddleware",
        "RequestLoggingASGIMiddleware",
    ]
    assert names.index("PrometheusASGIMiddleware") < names.index(
        "CustomCORSASGIMiddleware"
    )
    assert (
        names.index("SecurityHeadersMiddleware")
        < names.index("RateLimitASGIMiddleware")
        < names.index("CustomCORSASGIMiddleware")
        < names.index("RequestBodyLimitASGIMiddleware")
    )
    expected = [
        "SecurityHeadersMiddleware",
        "RateLimitASGIMiddleware",
        "HeaderSanitizationASGIMiddleware",
        "RequestHeaderLimitASGIMiddleware",
        "RequestTimeoutASGIMiddleware",
        "ContentTypeEnforcementASGIMiddleware",
        "MethodWhitelistASGIMiddleware",
        "CustomCORSASGIMiddleware",
        "RequestBodyLimitASGIMiddleware",
        "RequestErrorASGIMiddleware",
        "OperationalExposureASGIMiddleware",
    ]

    assert [name for name in names if name in expected] == expected


async def request(
    app: FastAPI,
    method: str = "GET",
    path: str = "/health",
    *,
    content: bytes | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, content=content, headers=headers)


async def test_stack_context_logging_cleanup_cors_security_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app: FastAPI = create_app()
    logger: Mock = Mock()
    count: Mock = Mock()

    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)
    monkeypatch.setattr("app.common.middleware.prometheus_metrics.REQUEST_COUNT", count)
    response = await request(app, path="/", headers={"origin": "https://client.test"})

    assert (
        response.status_code == 200
        and response.headers["access-control-allow-origin"] == "https://client.test"
        and response.headers["x-frame-options"] == "DENY"
    )
    assert RequestContext.get() is None
    logger.debug.assert_called()
    count.labels.assert_called()


async def test_stack_body_header_and_rate_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX", 12)
    app: FastAPI = create_app()

    assert (
        await request(
            app,
            "POST",
            content=b"x" * 1_048_577,
            headers={"content-type": "application/json"},
        )
    ).status_code == 413
    assert (await request(app, headers={"x-forwarded-for": "bad"})).status_code == 400
    for _ in range(10):
        assert (await request(app)).status_code in (200, 404)

    assert (await request(app)).status_code == 429


@pytest.mark.parametrize(
    'origin', ['https://client.test', 'https://blocked.test', None]
)
async def test_stack_downstream_exception_cleanup_and_server_error_boundary(
    origin: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    app: FastAPI = create_app()
    failure_log = Mock()
    access_log = Mock()
    count = Mock()

    monkeypatch.setattr('app.common.handlers.exception_handler.log', failure_log)
    monkeypatch.setattr('app.common.middleware.request_logger.log', access_log)
    monkeypatch.setattr('app.common.middleware.prometheus_metrics.REQUEST_COUNT', count)

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("boom")

    response = await request(
        app, path="/explode", headers={'origin': origin} if origin else None
    )

    assert response.status_code == (403 if origin == 'https://blocked.test' else 500)
    assert response.headers['x-request-id']
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers.get('access-control-allow-origin') == (
        origin if origin == 'https://client.test' else None
    )
    assert failure_log.error.call_count == (0 if response.status_code == 403 else 1)
    if response.status_code == 403:
        access_log.warning.assert_called_once()
    else:
        access_log.error.assert_called_once()

    count.labels.return_value.inc.assert_called_once()
    assert RequestContext.get() is None


@pytest.mark.parametrize(
    ('method', 'headers', 'expected'),
    [
        ('POST', {'content-type': 'text/plain', 'origin': 'https://blocked.test'}, 415),
        ('TRACE', {'origin': 'https://blocked.test'}, 405),
        (
            'POST',
            {'content-type': 'application/json', 'origin': 'https://blocked.test'},
            403,
        ),
        ('POST', {'content-type': 'application/json', 'x-forwarded-for': 'bad'}, 400),
        (
            'POST',
            {'content-type': 'application/json', 'x-requested-with': 'x' * 4096},
            431,
        ),
    ],
)
async def test_rejection_precedence_and_rate_accounting(
    method: str,
    headers: dict[str, str],
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, 'RATE_LIMIT_MAX', 1)
    app = create_app()
    response = await request(app, method, content=b'x' * 1_048_577, headers=headers)

    assert response.status_code == expected
    assert response.headers['x-request-id']
    assert response.headers['x-frame-options'] == 'DENY'
    assert 'access-control-allow-origin' not in response.headers
    assert (await request(app)).status_code == 429
