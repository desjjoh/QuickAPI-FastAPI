import httpx
import pytest
from fastapi.routing import APIRoute

from app.config.application import create_app
from app.config.environment import settings

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
            spellings = [path] if path == '/' else [path, path + '/']

            for spelling in spellings:
                response = await client.get(spelling)

                assert response.status_code == expected, (spelling, response.text)
                assert 'location' not in response.headers

            if path != '/':
                assert path + '/' not in schema['paths']
