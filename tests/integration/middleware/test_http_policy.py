from typing import Literal
from unittest.mock import Mock

import httpx
import pytest
from fastapi import Request

from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware
from app.common.store.rate_limit import RateLimitDecision
from app.common.store.request_context import RequestContext
from app.config.application import create_app
from app.config.environment import settings

from .test_timeout_server import running

pytestmark = pytest.mark.integration


async def test_cors_overrides_preflight_headers_and_no_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://ui.example"])
    monkeypatch.setattr(settings, "CORS_METHODS", ["GET", "POST"])
    monkeypatch.setattr(settings, "CORS_ALLOWED_HEADERS", ["content-type", "x-custom"])
    monkeypatch.setattr(settings, "CORS_EXPOSED_HEADERS", ["x-result"])
    monkeypatch.setattr(settings, "CORS_CREDENTIALS", False)
    monkeypatch.setattr(settings, "CORS_MAX_AGE_SECONDS", 90)
    monkeypatch.setattr(settings, "HTTP_ALLOWED_CONTENT_TYPES", ["text/plain"])
    app = create_app()

    @app.post("/custom")
    async def custom(request: Request) -> dict[str, str | None]:
        return {"custom": request.headers.get("x-custom")}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        headers = {
            "origin": "https://ui.example",
            "access-control-request-method": "POST",
            "access-control-request-headers": "Content-Type, X-Custom",
        }
        response = await client.options("/custom", headers=headers)

        assert response.status_code == 204
        assert response.headers["access-control-allow-origin"] == "https://ui.example"
        assert response.headers["access-control-allow-methods"] == "GET, POST"
        assert response.headers["access-control-max-age"] == "90"
        assert response.headers["vary"] == "Origin"
        assert "access-control-allow-credentials" not in response.headers
        assert (
            await client.options(
                "/custom",
                headers={**headers, "access-control-request-method": "DELETE"},
            )
        ).status_code == 403
        assert (
            await client.options(
                "/custom",
                headers={**headers, "access-control-request-headers": "x-denied"},
            )
        ).status_code == 403
        assert (
            await client.get("/", headers={"origin": "https://denied.example"})
        ).status_code == 403
        result = await client.post(
            "/custom",
            content="hello",
            headers={
                "origin": "https://ui.example",
                "content-type": "text/plain",
                "x-custom": "preserved",
            },
        )

        assert result.status_code == 200 and result.json() == {"custom": "preserved"}
        assert result.headers["access-control-expose-headers"] == "x-result"
        assert (await client.post("/custom", json={})).status_code == 415
        direct = await client.get("/")

        assert direct.status_code == 200
        assert not any(name.startswith("access-control-") for name in direct.headers)


async def test_configured_body_and_method_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "HTTP_MAX_BODY_BYTES", 10)
    monkeypatch.setattr(settings, "HTTP_ALLOWED_METHODS", ["GET", "POST", "OPTIONS"])
    monkeypatch.setattr(settings, "CORS_METHODS", ["GET", "POST", "OPTIONS"])
    app = create_app()

    @app.post("/body")
    async def body(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (
            await client.post(
                "/body", content=b"x" * 11, headers={"content-type": "application/json"}
            )
        ).status_code == 413
        accepted = await client.post(
            "/body", content=b"x" * 10, headers={"content-type": "application/json"}
        )

        assert accepted.status_code == 200 and accepted.json() == {"bytes": 10}
        assert (await client.put("/body", json={})).status_code == 405


@pytest.mark.parametrize("mode", ["count", "single", "total", "preflight"])
async def test_raw_header_limits_before_sanitization_and_cors(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://ui.example"])
    custom = {f"x-unknown-{index}": "v" for index in range(5)}

    if mode in {"count", "preflight"}:
        monkeypatch.setattr(settings, "HTTP_MAX_HEADER_COUNT", 6)
    elif mode == "single":
        monkeypatch.setattr(settings, "HTTP_MAX_SINGLE_HEADER_BYTES", 80)
        custom = {"x-unknown": "v" * 81}
    else:
        monkeypatch.setattr(settings, "HTTP_MAX_SINGLE_HEADER_BYTES", 100)
        monkeypatch.setattr(settings, "HTTP_MAX_TOTAL_HEADER_BYTES", 250)
        custom = {f"x-unknown-{index}": "v" * 60 for index in range(4)}

    app = create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        if mode == "preflight":
            result = await client.options(
                "/",
                headers={
                    **custom,
                    "origin": "https://ui.example",
                    "access-control-request-method": "GET",
                },
            )
        else:
            result = await client.get("/", headers=custom)

        assert result.status_code == 431
        assert result.json()["status"] == 431


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
@pytest.mark.parametrize("trusted", [False, True])
async def test_real_proxy_identity_shared_by_context_and_limiter(
    protocol: Literal["h11", "httptools"],
    trusted: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUST_PROXY", ["127.0.0.0/8"] if trusted else [])
    limiter = Mock(return_value=RateLimitDecision(allowed=True))

    monkeypatch.setattr("app.config.rate_limiter.RateLimiter.admit", limiter)
    app = create_app()

    @app.get("/identity")
    async def identity(request: Request) -> dict[str, str | None]:
        context = RequestContext.get()

        return {
            "ip": request.client.host if request.client else None,
            "context_ip": context.ip if context else None,
            "scheme": request.url.scheme,
        }

    async with running(app, protocol) as port:
        async with httpx.AsyncClient() as client:
            result = await client.get(
                f"http://127.0.0.1:{port}/identity",
                headers={
                    "x-forwarded-for": "192.0.2.99,198.51.100.8,127.0.0.2",
                    "x-forwarded-proto": "https",
                },
            )

            if trusted:
                assert result.status_code == 200
                assert result.json() == {
                    "ip": "198.51.100.8",
                    "context_ip": "198.51.100.8",
                    "scheme": "https",
                }
                limiter.assert_called_once_with("198.51.100.8")
            else:
                assert result.status_code == 400
                limiter.assert_called_once_with("127.0.0.1")


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_response_deadline_uses_configured_milliseconds(
    protocol: Literal["h11", "httptools"], monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    monkeypatch.setattr(settings, "REQUEST_TIMEOUT_MS", 120)
    monkeypatch.setattr(settings, "REQUEST_FIRST_BODY_TIMEOUT_MS", 80)
    monkeypatch.setattr(settings, "REQUEST_CHUNK_TIMEOUT_MS", 40)
    app = create_app()
    deadline = next(
        m for m in app.user_middleware if m.cls is RequestTimeoutASGIMiddleware
    )

    assert deadline.kwargs == {
        "first_body_timeout": 0.08,
        "chunk_timeout": 0.04,
        "total_timeout": 0.12,
        "work": app.state.request_work,
    }

    @app.get("/slow")
    async def slow() -> None:
        await asyncio.Event().wait()

    async with running(app, protocol) as port:
        async with httpx.AsyncClient() as client:
            result = await client.get(f"http://127.0.0.1:{port}/slow", timeout=2)

            assert result.status_code == 408
            assert result.json()["message"] == "Total request timeout exceeded."
