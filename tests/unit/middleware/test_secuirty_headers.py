import pytest
from conftest import RequestCall
from starlette.types import ASGIApp

from app.common.middleware.security_headers import SecurityHeadersMiddleware

pytestmark = pytest.mark.unit


async def test_headers_and_docs_bypass(app: ASGIApp, call: RequestCall) -> None:
    mw = SecurityHeadersMiddleware(app)
    normal = await call(mw)
    docs = await call(mw, path="/docs")
    assert (
        normal.headers["x-frame-options"] == "DENY"
        and normal.headers["content-security-policy"]
    )
    assert "x-frame-options" not in docs.headers
