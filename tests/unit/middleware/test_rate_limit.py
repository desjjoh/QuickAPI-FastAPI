import json
from unittest.mock import Mock

import pytest
from conftest import http_scope, invoke
from starlette.types import ASGIApp

from app.common.middleware.rate_limit import RateLimitASGIMiddleware
from app.common.store.rate_limit import RateLimitDecision
from app.config.rate_limiter import RateLimiter

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("status", [429, 503])
async def test_key_selection_rejection_body_and_headers(
    app: ASGIApp, status: int
) -> None:
    limiter = Mock()
    limiter.policy.window_ms = 2500
    limiter.policy.max_requests = 2
    limiter.admit.side_effect = [
        RateLimitDecision(True),
        RateLimitDecision(False, 429 if status == 429 else 503, 2),
    ]
    middleware = RateLimitASGIMiddleware(app, limiter)
    accepted = await invoke(middleware, http_scope(client=("4.3.2.1", 9)))
    rejected = await invoke(middleware, http_scope(client=("4.3.2.1", 9)))
    assert limiter.admit.call_args_list[0].args == ("4.3.2.1",)
    assert (b"x-ratelimit-result", b"accepted") in accepted[0]["headers"]
    headers = dict(rejected[0]["headers"])
    assert rejected[0]["status"] == status
    assert headers[b"retry-after"] == b"2"
    assert headers[b"x-ratelimit-result"] == b"rejected"
    payload = json.loads(rejected[1]["body"])
    assert set(payload) == {"status", "message", "timestamp"}
    assert payload["message"] == (
        "Rate limiter capacity is exhausted. Try again later."
        if status == 503
        else "Too many requests \u2014 limit is 2 per 2.5s."
    )


async def test_missing_peer_uses_one_shared_unknown_identity(app: ASGIApp) -> None:
    limiter = Mock()
    limiter.admit.return_value = RateLimitDecision(True)
    scope = http_scope()
    scope.pop("client", None)
    await invoke(RateLimitASGIMiddleware(app, limiter), scope)
    limiter.admit.assert_called_once_with("unknown")


@pytest.mark.parametrize("method", ["GET", "HEAD"])
async def test_favicon_bypasses_quota_with_mount_prefix(
    app: ASGIApp, method: str
) -> None:
    limiter = Mock()
    scope = http_scope(method=method, path="/service/favicon.ico")
    scope["root_path"] = "/service"
    await invoke(RateLimitASGIMiddleware(app, limiter), scope)
    limiter.admit.assert_not_called()


async def test_non_http_bypass(app: ASGIApp) -> None:
    limiter = Mock()
    await invoke(
        RateLimitASGIMiddleware(app, limiter), {"type": "websocket", "path": "/"}
    )
    limiter.admit.assert_not_called()


async def test_subsecond_window_message_retains_millisecond_precision(
    app: ASGIApp,
) -> None:
    def clock() -> float:
        return 0.0

    limiter = RateLimiter(window_ms=60001, max_requests=1, clock=clock)
    limiter.admit("1.2.3.4")
    sent = await invoke(RateLimitASGIMiddleware(app, limiter), http_scope())
    assert "60.001s" in json.loads(sent[1]["body"])["message"]
