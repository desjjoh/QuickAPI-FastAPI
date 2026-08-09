import time

import httpx
import pytest
from fastapi import FastAPI
from starlette.types import Message, Scope

from app.common.middleware.content_type_enforcement import (
    ContentTypeEnforcementASGIMiddleware,
)
from app.common.middleware.cors import CustomCORSASGIMiddleware
from app.common.middleware.method_whitelist import MethodWhitelistASGIMiddleware
from app.common.middleware.rate_limit import RateLimitASGIMiddleware
from app.common.middleware.request_body_limit import (
    BodyLimit,
    RequestBodyLimitASGIMiddleware,
)
from app.common.middleware.request_header_limit import (
    HeaderLimits,
    RequestHeaderLimitASGIMiddleware,
)
from app.common.middleware.request_header_sanitization import (
    HeaderSanitizationASGIMiddleware,
)
from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware
from app.config.rate_limiter import RateLimiter

from .test_error_responses import assert_error_contract

pytestmark = pytest.mark.integration


def rejecting_app(kind: str) -> FastAPI:
    app = FastAPI()

    @app.get("/")
    @app.post("/")
    async def endpoint() -> dict[str, bool]:
        return {"ok": True}

    if kind == "400":
        app.add_middleware(HeaderSanitizationASGIMiddleware)
    elif kind == "403":
        app.add_middleware(
            CustomCORSASGIMiddleware,
            origin=["https://allowed.example"],
            methods=["GET"],
            allowed_headers=[],
            exposed_headers=[],
        )
    elif kind == "405":
        app.add_middleware(MethodWhitelistASGIMiddleware, allowed_methods={"GET"})
    elif kind == "408":
        app.add_middleware(RequestTimeoutASGIMiddleware, header_timeout=0)
    elif kind == "413":
        app.add_middleware(RequestBodyLimitASGIMiddleware, default_limit=BodyLimit(2))
    elif kind == "415":
        app.add_middleware(ContentTypeEnforcementASGIMiddleware)
    elif kind == "429":
        limiter = RateLimiter(
            max_burst=0, burst_window=5, max_sustained=0, sustained_period=60
        )
        app.add_middleware(RateLimitASGIMiddleware, limiter=limiter)
    else:
        app.add_middleware(
            RequestHeaderLimitASGIMiddleware,
            limits=HeaderLimits(max_header_count=1, allow_chunked=False),
        )
    return app


@pytest.mark.parametrize(
    ("kind", "method", "headers", "content", "expected"),
    [
        ("400", "GET", {"x-forwarded-for": "secret"}, None, 400),
        ("403", "GET", {"origin": "https://denied.example"}, None, 403),
        ("405", "TRACE", {}, None, 405),
        ("408", "GET", {}, None, 408),
        ("413", "POST", {"content-type": "application/json"}, b"abc", 413),
        ("415", "POST", {}, b"{}", 415),
        ("429", "GET", {}, None, 429),
        ("431", "GET", {"x-one": "1"}, None, 431),
    ],
)
async def test_every_middleware_rejection_status_uses_error_response(
    kind: str,
    method: str,
    headers: dict[str, str],
    content: bytes | None,
    expected: int,
) -> None:
    app = rejecting_app(kind)
    started = int(time.time() * 1000)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.request(method, "/", headers=headers, content=content)
    assert_error_contract(response, expected, started_ms=started)
    if expected == 429:
        assert response.headers["x-ratelimit-result"] == "rejected"


async def test_chunked_request_rejection_is_documented_envelope() -> None:
    app = FastAPI()
    app.add_middleware(RequestHeaderLimitASGIMiddleware, limits=HeaderLimits())

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(b"transfer-encoding", b"chunked")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    started = int(time.time() * 1000)
    await app(scope, receive, send)
    start = messages[0]
    body = messages[1]["body"]
    assert isinstance(start["status"], int)
    assert isinstance(body, bytes)
    response = httpx.Response(
        status_code=start["status"],
        headers=start["headers"],
        content=body,
    )
    assert_error_contract(response, 501, started_ms=started)
