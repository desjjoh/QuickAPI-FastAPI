import asyncio
from collections.abc import AsyncGenerator
from typing import Literal
from unittest.mock import Mock

import anyio
import httpx
import pytest
import structlog
from fastapi import Request
from prometheus_client import Counter, Histogram
from prometheus_client.samples import Sample
from starlette.responses import StreamingResponse

from app.common.middleware.request_outcome import RequestOutcomeASGIMiddleware
from app.common.store.rate_limit import RateLimitDecision
from app.common.store.request_context import RequestContext
from app.config.application import create_app
from app.config.environment import settings
from app.config.metrics import REQUEST_ABORTED, REQUEST_COUNT, REQUEST_DURATION

from .test_timeout_server import application, running

pytestmark = pytest.mark.integration


def samples(metric: Counter | Histogram, name: str) -> list[Sample]:
    return [
        sample
        for family in metric.collect()
        for sample in family.samples
        if sample.name == name
    ]


async def test_bounded_routes_methods_and_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()

    monkeypatch.setattr(
        "app.config.rate_limiter.RateLimiter.admit",
        Mock(return_value=RateLimitDecision(allowed=True)),
    )
    logger = Mock()

    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)

    @app.get("/entries/{entry_id}")
    async def entry(entry_id: int) -> dict[str, int]:
        return {"id": entry_id}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for value in range(30):
            assert (
                await client.get(f"/entries/{value}?private=secret-{value}")
            ).status_code == 200
            assert (await client.get(f"/missing/secret-{value}")).status_code == 404
            assert (await client.request(f"PRIVATE-{value}", "/")).status_code == 405

        assert (await client.post("/entries/1", json={})).status_code == 405

    completed = samples(REQUEST_COUNT, "http_requests_total")

    assert {
        (s.labels["method"], s.labels["route"], s.labels["status"]) for s in completed
    } == {
        ("GET", "/entries/{entry_id}", "200"),
        ("GET", "<unmatched>", "404"),
        ("<other>", "<unmatched>", "405"),
        ("POST", "/entries/{entry_id}", "405"),
    }
    assert sum(s.value for s in completed) == 91
    assert not samples(REQUEST_ABORTED, "http_requests_aborted_total")
    assert "secret-" not in str(logger.mock_calls)
    assert "PRIVATE-" not in str(logger.mock_calls)
    buckets = samples(REQUEST_DURATION, "http_request_duration_ms_bucket")

    assert {s.labels["le"] for s in buckets} == {
        "5.0",
        "15.0",
        "50.0",
        "100.0",
        "250.0",
        "500.0",
        "1000.0",
        "+Inf",
    }
    assert all(set(s.labels) == {"method", "route", "status", "le"} for s in buckets)


async def test_actual_500_and_policy_rejections_are_completed_once_with_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX", 12)
    app = create_app()
    # Three rejected/failed requests and nine probes consume twelve admissions.
    # Use an explicit test quota rather than coupling this test to production defaults.
    records: list[tuple[str, str | None]] = []
    expected_ids: list[str] = []

    def capture(message: str, **fields: object) -> None:
        records.append(
            (message, structlog.contextvars.get_contextvars().get("request_id"))
        )

    logger = Mock()
    logger.error.side_effect = capture
    logger.warning.side_effect = capture

    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)

    @app.get("/explode")
    async def explode() -> None:
        context = RequestContext.get()

        assert context is not None
        expected_ids.append(context.request_id)

        raise RuntimeError("broken")

    assert isinstance(app.build_middleware_stack(), RequestOutcomeASGIMiddleware)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        assert (
            await client.get("/explode", headers={"x-request-id": "error-request"})
        ).status_code == 500
        body_response = await client.post(
            "/",
            content=b"x" * 1_048_577,
            headers={
                "x-request-id": "body-request",
                "content-type": "application/json",
            },
        )

        assert body_response.status_code == 413
        expected_ids.append(body_response.headers["x-request-id"])
        header_response = await client.get("/", headers={"x-forwarded-for": "bad"})

        assert header_response.status_code == 400
        expected_ids.append(header_response.headers["x-request-id"])
        for _ in range(9):
            await client.get("/health")

        limit_response = await client.get("/")

        assert limit_response.status_code == 429
        expected_ids.append(limit_response.headers["x-request-id"])

    assert {
        (s.labels["route"], s.labels["status"], s.value)
        for s in samples(REQUEST_COUNT, "http_requests_total")
    } == {
        ("/explode", "500", 1),
        ("<unmatched>", "413", 1),
        ("<unmatched>", "400", 1),
        ("<unmatched>", "429", 1),
    }
    assert [request_id for _, request_id in records] == expected_ids
    assert len(set(expected_ids)) == 4
    logger.error.assert_called_once()
    assert logger.warning.call_count == 3
    assert all("ABORTED" not in message for message, _ in records)
    assert not samples(REQUEST_ABORTED, "http_requests_aborted_total")
    assert not structlog.contextvars.get_contextvars()


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
@pytest.mark.parametrize("mode", ["timeout", "disconnect"])
async def test_real_outcome_before_cleanup(
    protocol: Literal["h11", "httptools"], mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = application(total_timeout=0.15 if mode == "timeout" else 2)
    entered = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()
    logger = Mock()

    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)

    @app.get("/slow/{entry_id}")
    async def slow(entry_id: int) -> dict[str, int]:
        entered.set()

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            cleaned.set()

        return {"id": entry_id}

    async with running(app, protocol) as port:
        try:
            if mode == "timeout":
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"http://127.0.0.1:{port}/slow/123")

                    assert response.status_code == 408
            else:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)

                writer.write(b"GET /slow/123 HTTP/1.1\r\nHost: test\r\n\r\n")
                await writer.drain()
                await asyncio.wait_for(entered.wait(), 1)
                writer.close()
                await writer.wait_closed()
                del reader

            async with asyncio.timeout(1):
                while not logger.warning.called:
                    await asyncio.sleep(0.001)

            assert not cleaned.is_set()
            completed = samples(REQUEST_COUNT, "http_requests_total")
            aborted = samples(REQUEST_ABORTED, "http_requests_aborted_total")

            if mode == "timeout":
                assert len(completed) == 1 and completed[0].labels == {
                    "method": "GET",
                    "route": "/slow/{entry_id}",
                    "status": "408",
                }
                assert completed[0].value == 1 and not aborted
                assert (
                    len(samples(REQUEST_DURATION, "http_request_duration_ms_count"))
                    == 1
                )
            else:
                assert not completed and not samples(
                    REQUEST_DURATION, "http_request_duration_ms_count"
                )
                assert len(aborted) == 1 and aborted[0].labels == {
                    "method": "GET",
                    "route": "/slow/{entry_id}",
                }
                assert aborted[0].value == 1
                assert "ABORTED" in logger.warning.call_args.args[0]

            release.set()
            await asyncio.wait_for(cleaned.wait(), 1)
            await asyncio.sleep(0.01)
            logger.warning.assert_called_once()
            assert samples(REQUEST_COUNT, "http_requests_total") == completed
            assert samples(REQUEST_ABORTED, "http_requests_aborted_total") == aborted
        finally:
            release.set()
            await asyncio.wait_for(cleaned.wait(), 1)


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
@pytest.mark.parametrize("mode", ["timeout", "disconnect"])
async def test_real_stream_abort_is_not_a_completed_200(
    protocol: Literal["h11", "httptools"], mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = application(total_timeout=0.15 if mode == "timeout" else 2)
    release = asyncio.Event()
    cleaned = asyncio.Event()
    logger = Mock()

    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)

    async def chunks() -> AsyncGenerator[bytes, None]:
        try:
            yield b"partial"
            await asyncio.Event().wait()
        finally:
            with anyio.CancelScope(shield=True):
                await release.wait()
                cleaned.set()

    @app.get("/stream/{entry_id}")
    async def stream(entry_id: int) -> StreamingResponse:
        return StreamingResponse(chunks())

    async with running(app, protocol) as port:
        try:
            if mode == "timeout":
                async with httpx.AsyncClient() as client:
                    with pytest.raises(httpx.RemoteProtocolError):
                        async with client.stream(
                            "GET", f"http://127.0.0.1:{port}/stream/123"
                        ) as response:
                            assert response.status_code == 200
                            async for _ in response.aiter_bytes():
                                pass
            else:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)

                writer.write(b"GET /stream/123 HTTP/1.1\r\nHost: test\r\n\r\n")
                await writer.drain()
                async with asyncio.timeout(1):
                    await reader.readuntil(b"partial")

                writer.close()
                await writer.wait_closed()

            async with asyncio.timeout(1):
                while not logger.warning.called:
                    await asyncio.sleep(0.001)

            assert not cleaned.is_set()
            assert not samples(REQUEST_COUNT, "http_requests_total")
            assert not samples(REQUEST_DURATION, "http_request_duration_ms_count")
            aborted = samples(REQUEST_ABORTED, "http_requests_aborted_total")

            assert len(aborted) == 1 and aborted[0].value == 1
            assert aborted[0].labels == {"method": "GET", "route": "/stream/{entry_id}"}
            assert "ABORTED" in logger.warning.call_args.args[0]
            release.set()
            await asyncio.wait_for(cleaned.wait(), 1)
            await asyncio.sleep(0.01)
            logger.warning.assert_called_once()
            assert samples(REQUEST_ABORTED, "http_requests_aborted_total") == aborted
        finally:
            release.set()
            await asyncio.wait_for(cleaned.wait(), 1)


async def test_concurrent_requests_keep_their_context_and_shared_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    identities: dict[str, str] = {}
    messages: dict[str, str] = {}
    both_entered = asyncio.Event()

    def capture(message: str, **fields: object) -> None:
        request_id = structlog.contextvars.get_contextvars().get("request_id")

        assert isinstance(request_id, str)
        messages[request_id] = message

    logger = Mock()
    logger.debug.side_effect = capture

    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)

    @app.get("/first")
    @app.get("/second")
    async def endpoint(request: Request) -> dict[str, bool]:
        context = RequestContext.get()

        assert context is not None
        identities[request.url.path] = context.request_id

        if len(identities) == 2:
            both_entered.set()

        await asyncio.wait_for(both_entered.wait(), 1)

        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(client.get("/first"), client.get("/second"))

    assert all(response.status_code == 200 for response in responses)
    assert len(messages) == 2 and len(set(identities.values())) == 2
    for path, request_id in identities.items():
        assert path in messages[request_id]
        elapsed = float(messages[request_id].split()[-1].removesuffix("ms"))
        recorded = next(
            s.value
            for s in samples(REQUEST_DURATION, "http_request_duration_ms_sum")
            if s.labels["route"] == path
        )

        assert elapsed == pytest.approx(recorded, abs=0.006)
