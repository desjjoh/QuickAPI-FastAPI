from typing import Any, cast
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from starlette.types import ASGIApp

from app.common.middleware.content_type_enforcement import (
    ContentTypeEnforcementASGIMiddleware,
)
from app.common.middleware.cors import CustomCORSASGIMiddleware
from app.common.middleware.method_whitelist import MethodWhitelistASGIMiddleware
from app.common.middleware.prometheus_metrics import PrometheusASGIMiddleware
from app.common.middleware.rate_limit import RateLimitASGIMiddleware
from app.common.middleware.request_body_limit import (
    BodyLimit,
    RequestBodyLimitASGIMiddleware,
)
from app.common.middleware.request_cleanup import RequestCleanupASGIMiddleware
from app.common.middleware.request_context import RequestContextASGIMiddleware
from app.common.middleware.request_header_limit import (
    HeaderLimits,
    RequestHeaderLimitASGIMiddleware,
)
from app.common.middleware.request_header_sanitization import (
    HeaderSanitizationASGIMiddleware,
)
from app.common.middleware.request_logger import RequestLoggingASGIMiddleware
from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware
from app.common.middleware.security_headers import SecurityHeadersMiddleware
from app.common.store.request_context import RequestContext
from app.config.rate_limiter import RateLimiter

pytestmark = pytest.mark.unit


def base_app() -> FastAPI:
    app = FastAPI()

    @app.api_route("/echo", methods=["GET", "POST", "OPTIONS"])
    async def echo() -> dict[str, object | None]:
        ctx = RequestContext.get()
        return {"ok": True, "request_id": ctx.request_id if ctx else None}

    return app


async def request(app: ASGIApp, method: str = "GET", **kwargs: Any) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, "/echo", **kwargs)


@pytest.mark.asyncio
async def test_method_content_type_and_body_limits_accept_and_reject() -> None:
    methods = MethodWhitelistASGIMiddleware(base_app(), {"GET"})
    assert (await request(methods)).status_code == 200
    assert (await request(methods, "TRACE")).status_code == 405

    content = ContentTypeEnforcementASGIMiddleware(base_app())
    assert (await request(content, "POST", json={})).status_code == 200
    assert (
        await request(
            content, "POST", content=b"x", headers={"content-type": "text/plain"}
        )
    ).status_code == 415
    assert (
        await request(content, "GET", headers={"content-type": "application/json"})
    ).status_code == 415

    body = RequestBodyLimitASGIMiddleware(base_app(), default_limit=BodyLimit(8))
    accepted = await request(body, "POST", content=b"12345678")
    assert accepted.status_code == 200 and accepted.headers["x-body-limit-bytes"] == "8"
    assert (await request(body, "POST", content=b"123456789")).status_code == 413


@pytest.mark.asyncio
async def test_header_limit_and_sanitization_accept_and_reject() -> None:
    limits = RequestHeaderLimitASGIMiddleware(
        base_app(),
        HeaderLimits(
            max_header_count=10, max_single_header_bytes=30, max_total_header_bytes=100
        ),
    )
    assert (await request(limits)).status_code == 200
    assert (await request(limits, headers={"x-long": "x" * 40})).status_code == 431

    sanitize = HeaderSanitizationASGIMiddleware(base_app(), extra_allowed={"x-custom"})
    assert (await request(sanitize, headers={"x-custom": "safe"})).status_code == 200
    assert (
        await request(sanitize, headers={"x-forwarded-for": "127.0.0.1"})
    ).status_code == 400


@pytest.mark.asyncio
async def test_cors_security_metrics_and_rate_limit() -> None:
    cors = CustomCORSASGIMiddleware(
        base_app(),
        origin=["https://allowed.test"],
        methods=["GET", "OPTIONS"],
        allowed_headers=["content-type"],
        exposed_headers=[],
        credentials=True,
    )
    accepted = await request(cors, headers={"origin": "https://allowed.test"})
    assert accepted.headers["access-control-allow-origin"] == "https://allowed.test"
    assert (
        await request(cors, headers={"origin": "https://evil.test"})
    ).status_code == 403
    preflight = await request(
        cors, "OPTIONS", headers={"origin": "https://allowed.test"}
    )
    assert preflight.status_code == 204

    secured = SecurityHeadersMiddleware(base_app())
    assert (await request(secured)).headers["x-frame-options"] == "DENY"
    measured = PrometheusASGIMiddleware(base_app())
    assert (await request(measured)).status_code == 200

    limiter = Mock()
    limiter.allow.side_effect = [True, False]
    limited = RateLimitASGIMiddleware(base_app(), cast(RateLimiter, limiter))
    assert (await request(limited)).status_code == 200
    assert (await request(limited)).status_code == 429


@pytest.mark.asyncio
async def test_context_cleanup_logging_order_interaction() -> None:
    # Cleanup must be outermost so context remains available to logging/handlers,
    # but is always cleared after the response completes.
    stack = RequestCleanupASGIMiddleware(
        RequestContextASGIMiddleware(RequestLoggingASGIMiddleware(base_app()))
    )
    response = await request(stack)
    assert response.status_code == 200 and response.json()["request_id"]
    assert RequestContext.get() is None


@pytest.mark.asyncio
async def test_timeout_middleware_accepts_normal_requests_and_rejects_expired_headers() -> (
    None
):
    normal = RequestTimeoutASGIMiddleware(base_app(), header_timeout=1)
    assert (await request(normal)).status_code == 200
    expired = RequestTimeoutASGIMiddleware(base_app(), header_timeout=0)
    assert (await request(expired)).status_code == 408
