import pytest
from conftest import invoke
from starlette.types import ASGIApp, Scope

from app.common.middleware.operational_exposure import OperationalExposureASGIMiddleware

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("scope", [{"type": "websocket"}, {"type": "lifespan"}])
async def test_non_http_is_passthrough(scope: Scope, app: ASGIApp) -> None:
    wrapped = OperationalExposureASGIMiddleware(
        app, docs_enabled=False, diagnostics_enabled=False, metrics_enabled=False
    )
    result = await invoke(wrapped, scope)

    assert result[0]["type"] == f"{scope['type']}.response.start"
