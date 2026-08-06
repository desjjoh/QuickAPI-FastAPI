import pytest
from conftest import RequestCall, invoke
from starlette.types import ASGIApp

from app.common.middleware.method_whitelist import MethodWhitelistASGIMiddleware

pytestmark = pytest.mark.unit


async def test_accepted_rejected_casing_and_non_http(
    app: ASGIApp, call: RequestCall
) -> None:
    mw = MethodWhitelistASGIMiddleware(app, {"get"})
    assert (await call(mw)).status_code == 200 and (
        await call(mw, "POST")
    ).status_code == 405
    assert (await invoke(mw, {"type": "websocket", "path": "/"}))[0]["status"] == 200
