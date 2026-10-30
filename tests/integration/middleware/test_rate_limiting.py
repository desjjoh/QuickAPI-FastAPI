import asyncio
from typing import Literal, cast

import httpx
import pytest
from fastapi import FastAPI

from app.common.middleware.rate_limit import RateLimitASGIMiddleware
from app.config.application import create_app
from app.config.environment import settings
from app.config.rate_limiter import RateLimiter

from .test_timeout_server import running

pytestmark = pytest.mark.integration


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def seconds(self) -> float:
        return self.now / 1000


def application(
    monkeypatch: pytest.MonkeyPatch, *, max_requests: int = 2, max_clients: int = 10
) -> tuple[FastAPI, Clock]:
    clock = Clock()

    monkeypatch.setattr("app.config.rate_limiter.monotonic", clock.seconds)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_MS", 2500)
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX", max_requests)
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_CLIENTS", max_clients)

    return create_app(), clock


def limiter_for(app: FastAPI) -> RateLimiter:
    return cast(
        RateLimiter,
        next(
            middleware.kwargs["limiter"]
            for middleware in app.user_middleware
            if middleware.cls is RateLimitASGIMiddleware
        ),
    )


async def test_remaining_delay_and_exact_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, clock = application(monkeypatch)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (await client.get("/")).status_code == 200
        clock.now = 1000

        assert (await client.get("/")).status_code == 200
        clock.now = 1250
        result = await client.get("/")

        assert result.status_code == 429
        assert result.headers["retry-after"] == "2"
        assert result.headers["x-ratelimit-result"] == "rejected"
        assert (
            result.json()["message"] == "Too many requests \u2014 limit is 2 per 2.5s."
        )
        assert set(result.json()) == {"status", "message", "timestamp"}
        clock.now = 2500
        accepted = await client.get("/")

        assert accepted.status_code == 200
        assert "retry-after" not in accepted.headers


async def test_capacity_retains_existing_quota_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUST_PROXY", ["127.0.0.1"])
    app, clock = application(monkeypatch, max_clients=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:

        async def get(ip: str) -> httpx.Response:
            return await client.get("/", headers={"x-forwarded-for": ip})

        assert (await get("198.51.100.1")).status_code == 200
        clock.now = 1001
        full = await get("198.51.100.2")

        assert full.status_code == 503 and full.headers["retry-after"] == "2"
        assert (
            full.json()["message"]
            == "Rate limiter capacity is exhausted. Try again later."
        )
        assert full.headers["x-ratelimit-result"] == "rejected"
        assert (await get("198.51.100.1")).status_code == 200
        assert (await get("198.51.100.1")).status_code == 429
        assert limiter_for(app).usage.clients == 1
        clock.now = 3501

        assert (await get("198.51.100.2")).status_code == 200


async def test_untrusted_forwarding_cannot_allocate_new_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUST_PROXY", [])
    app, _ = application(monkeypatch, max_clients=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for index in range(2):
            assert (
                await client.get(
                    "/", headers={"x-forwarded-for": f"198.51.100.{index}"}
                )
            ).status_code == 400

        assert (
            await client.get("/", headers={"x-forwarded-for": "198.51.100.3"})
        ).status_code == 429

    assert limiter_for(app).usage.clients == 1
    assert limiter_for(app).usage.stored_requests == 2


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/health", 200),
        ("/ready", 503),
        ("/info", 200),
        ("/system", 200),
        ("/metrics", 200),
        ("/docs", 200),
        ("/openapi.json", 200),
        ("/missing", 404),
    ],
)
async def test_probes_and_other_endpoints_share_quota(
    path: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = application(monkeypatch, max_requests=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (await client.get(path)).status_code == expected
        limited = await client.get("/")

        assert limited.status_code == 429 and limited.headers["retry-after"] == "3"


async def test_preflight_counts_and_rejection_precedes_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = application(monkeypatch, max_requests=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        preflight = await client.options(
            "/",
            headers={
                "origin": "http://localhost:3000",
                "access-control-request-method": "GET",
            },
        )

        assert preflight.status_code == 204
        assert preflight.headers["x-ratelimit-result"] == "accepted"
        rejected = await client.get("/", headers={"origin": "http://localhost:3000"})

        assert rejected.status_code == 429 and rejected.headers["retry-after"] == "3"
        assert rejected.headers["x-frame-options"] == "DENY"
        assert "access-control-allow-origin" not in rejected.headers


async def test_raw_header_rejection_does_not_consume_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "HTTP_MAX_HEADER_COUNT", 6)
    app, _ = application(monkeypatch, max_requests=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        rejected = await client.get(
            "/", headers={f"x-extra-{index}": "value" for index in range(10)}
        )

        assert rejected.status_code == 431
        assert limiter_for(app).usage.clients == 0
        assert (await client.get("/")).status_code == 200


async def test_favicon_get_head_are_exempt_but_post_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = application(monkeypatch, max_requests=1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for _ in range(3):
            assert (await client.get("/favicon.ico")).status_code == 200
            assert (await client.head("/favicon.ico")).status_code == 200

        assert limiter_for(app).usage.clients == 0
        assert (await client.post("/favicon.ico", json={})).status_code == 405
        assert (await client.get("/")).status_code == 429
        assert (await client.get("/favicon.ico")).status_code == 200


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_concurrent_burst_capacity_and_recovery(
    protocol: Literal["h11", "httptools"], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TRUST_PROXY", ["127.0.0.1"])
    app, clock = application(monkeypatch, max_requests=5, max_clients=2)

    async with running(app, protocol) as port:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            responses = await asyncio.gather(
                *(
                    client.get("/", headers={"x-forwarded-for": "198.51.100.1"})
                    for _ in range(20)
                )
            )

            assert sum(response.status_code == 200 for response in responses) == 5
            rejected = [
                response for response in responses if response.status_code == 429
            ]

            assert len(rejected) == 15
            assert all(response.headers["retry-after"] == "3" for response in rejected)
            assert (
                await client.get("/", headers={"x-forwarded-for": "198.51.100.2"})
            ).status_code == 200
            assert (
                await client.get("/", headers={"x-forwarded-for": "198.51.100.3"})
            ).status_code == 503
            assert limiter_for(app).usage.clients == 2
            clock.now = 2500

            assert (
                await client.get("/", headers={"x-forwarded-for": "198.51.100.3"})
            ).status_code == 200
            assert limiter_for(app).usage.clients == 1
