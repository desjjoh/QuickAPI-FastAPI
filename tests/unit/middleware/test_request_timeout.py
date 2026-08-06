import asyncio

import pytest
from conftest import http_scope, invoke
from starlette.types import Receive, Scope, Send

from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware

pytestmark = pytest.mark.unit


async def respond(send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body"})


async def test_normal_and_exception() -> None:
    async def normal(scope: Scope, receive: Receive, send: Send) -> None:
        await respond(send)

    assert (
        await invoke(
            RequestTimeoutASGIMiddleware(normal, total_timeout=0.1), http_scope()
        )
    )[0]["status"] == 200

    async def broken(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await invoke(RequestTimeoutASGIMiddleware(broken), http_scope())


async def test_timeout_cancels_and_cleans_downstream() -> None:
    cleaned = asyncio.Event()

    async def slow(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await asyncio.sleep(1)
        finally:
            cleaned.set()

    sent = await invoke(
        RequestTimeoutASGIMiddleware(slow, total_timeout=0.01), http_scope()
    )
    assert sent[0]["status"] == 408 and cleaned.is_set()


async def test_header_timeout_and_streaming_response() -> None:
    async def stream(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"a", "more_body": True})
        await send({"type": "http.response.body", "body": b"b"})

    assert (
        await invoke(
            RequestTimeoutASGIMiddleware(stream, total_timeout=0.1), http_scope()
        )
    )[-1]["body"] == b"b"
    assert (
        await invoke(
            RequestTimeoutASGIMiddleware(stream, header_timeout=0), http_scope()
        )
    )[0]["status"] == 408
