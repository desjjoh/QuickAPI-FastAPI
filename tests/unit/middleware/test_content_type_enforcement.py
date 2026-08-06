import pytest
from conftest import RequestCall
from starlette.types import ASGIApp

from app.common.middleware.content_type_enforcement import (
    ContentTypeEnforcementASGIMiddleware,
)

pytestmark = pytest.mark.unit


async def test_http_accept_reject_boundaries_and_bypass(
    app: ASGIApp, call: RequestCall
) -> None:
    mw = ContentTypeEnforcementASGIMiddleware(app)
    assert (
        await call(
            mw,
            "POST",
            content=b"{}",
            headers={"content-type": "application/json; charset=utf-8"},
        )
    ).status_code == 200
    assert (
        await call(mw, "POST", content=b"x", headers={"content-type": "text/plain"})
    ).status_code == 415
    assert (
        await call(mw, "GET", headers={"content-type": "application/json"})
    ).status_code == 415
