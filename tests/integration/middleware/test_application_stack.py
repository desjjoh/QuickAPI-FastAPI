from collections.abc import Mapping
from typing import cast
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI

from app.common.store.request_context import RequestContext
from app.config.application import create_app

pytestmark = pytest.mark.integration


def test_configured_order_is_explicit() -> None:
    app: FastAPI = create_app()
    names: list[str] = [
        cast(type[object], middleware.cls).__name__
        for middleware in app.user_middleware
    ]
    assert names[:3] == [
        "RequestCleanupASGIMiddleware",
        "RequestContextASGIMiddleware",
        "RequestLoggingASGIMiddleware",
    ]
    assert (
        names.index("CustomCORSASGIMiddleware")
        < names.index("SecurityHeadersMiddleware")
        < names.index("RequestBodyLimitASGIMiddleware")
    )
    assert (
        names.index("RequestHeaderLimitASGIMiddleware")
        < names.index("RateLimitASGIMiddleware")
        < names.index("RequestTimeoutASGIMiddleware")
        < names.index("PrometheusASGIMiddleware")
    )


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
    response = await request(app, headers={"origin": "https://client.test"})
    assert (
        response.status_code == 200
        and response.headers["access-control-allow-origin"] == "https://client.test"
        and response.headers["x-frame-options"] == "DENY"
    )
    assert RequestContext.get() is None
    logger.info.assert_called()
    count.labels.assert_called()


async def test_stack_body_header_and_rate_rejections() -> None:
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


async def test_stack_downstream_exception_cleanup_and_server_error_boundary() -> None:
    app: FastAPI = create_app()

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("boom")

    response = await request(
        app, path="/explode", headers={"origin": "https://client.test"}
    )
    assert response.status_code == 500
    # Starlette's ServerErrorMiddleware is outside the configured user middleware.
    # Its fallback response therefore does not pass through CORS/security wrappers.
    assert "access-control-allow-origin" not in response.headers
    assert "x-frame-options" not in response.headers
    assert RequestContext.get() is None
