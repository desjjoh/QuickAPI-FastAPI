from unittest.mock import Mock

import pytest
from conftest import http_scope, invoke
from starlette.types import ASGIApp

from app.common.middleware.rate_limit import RateLimitASGIMiddleware
from app.config.rate_limiter import RateLimiter

pytestmark = pytest.mark.unit


async def test_key_selection_accept_reject_headers(app: ASGIApp) -> None:
    limiter = Mock()
    limiter.allow.side_effect = [True, False]
    mw = RateLimitASGIMiddleware(app, limiter)
    first = await invoke(mw, http_scope(client=("4.3.2.1", 9)))
    second = await invoke(mw, http_scope(client=("4.3.2.1", 9)))
    assert limiter.allow.call_args_list[0].args == ("4.3.2.1",)
    assert (b"x-ratelimit-result", b"accepted") in first[0]["headers"] and second[0][
        "status"
    ] == 429


async def test_independent_clients_and_controlled_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [10.0]
    monkeypatch.setattr("app.config.rate_limiter.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.common.store.rate_limit.monotonic", lambda: clock[0])
    limiter = RateLimiter(
        max_burst=1, burst_window=5, max_sustained=10, sustained_period=10
    )
    assert limiter.allow("a") and not limiter.allow("a") and limiter.allow("b")
    clock[0] = 15.0
    assert limiter.allow("a")


async def test_non_http_bypass(app: ASGIApp) -> None:
    limiter = Mock()
    await invoke(
        RateLimitASGIMiddleware(app, limiter), {"type": "websocket", "path": "/"}
    )
    limiter.allow.assert_not_called()
