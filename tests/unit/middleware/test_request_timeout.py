import asyncio
import json
from unittest.mock import Mock

import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware

pytestmark = pytest.mark.unit
SCOPE: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}


class Transport:
    def __init__(self, messages: list[Message] | None = None) -> None:
        self.incoming: asyncio.Queue[Message] = asyncio.Queue()

        for message in messages or []:
            self.incoming.put_nowait(message)

        self.sent: list[Message] = []
        self.finished = asyncio.Event()

    async def receive(self) -> Message:
        return await self.incoming.get()

    async def send(self, message: Message) -> None:
        self.sent.append(message)
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            self.finished.set()

    async def run(self, app: ASGIApp) -> None:
        await asyncio.wait_for(app(SCOPE, self.receive, self.send), timeout=1)


async def respond(send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def assert_timeout(transport: Transport, message: str) -> None:
    assert [
        m["status"] for m in transport.sent if m["type"] == "http.response.start"
    ] == [408]
    body = json.loads(transport.sent[-1]["body"])

    assert body["status"] == 408 and body["message"] == message
    assert isinstance(body["timestamp"], int)


async def test_normal_stream_and_post_response_cleanup_do_not_expire() -> None:
    release = asyncio.Event()
    transport = Transport()

    async def stream(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"a", "more_body": True})
        await send({"type": "http.response.body", "body": b"b"})
        await release.wait()

    task = asyncio.create_task(
        transport.run(RequestTimeoutASGIMiddleware(stream, total_timeout=0.02))
    )

    try:
        await asyncio.wait_for(transport.finished.wait(), 1)
        await asyncio.sleep(0.04)
        assert not task.done()
        assert [m.get("body") for m in transport.sent[1:]] == [b"a", b"b"]
    finally:
        release.set()
        await task


@pytest.mark.parametrize("error", [RuntimeError("boom"), TimeoutError("dependency")])
async def test_downstream_errors_are_not_reclassified(error: Exception) -> None:
    async def broken(scope: Scope, receive: Receive, send: Send) -> None:
        raise error

    transport = Transport()

    with pytest.raises(type(error)) as caught:
        await transport.run(RequestTimeoutASGIMiddleware(broken))

    assert caught.value is error
    assert transport.sent == []


async def test_total_timeout_cancels_work_and_runs_async_cleanup() -> None:
    cleaning = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()
    transport = Transport()

    async def slow(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()
            await respond(send)  # Late output from cleanup must be suppressed.

    middleware = RequestTimeoutASGIMiddleware(slow, total_timeout=0.01)

    try:
        await transport.run(middleware)
        assert_timeout(transport, "Total request timeout exceeded.")
        await asyncio.wait_for(cleaning.wait(), 1)
        assert not cleaned.is_set()
    finally:
        release.set()
        await asyncio.wait_for(cleaned.wait(), 1)

    assert len(transport.sent) == 2


async def test_stream_timeout_never_completes_or_replaces_partial_response() -> None:
    cleaned = asyncio.Event()
    transport = Transport()

    async def stream(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send(
                {"type": "http.response.body", "body": b"partial", "more_body": True}
            )
            await asyncio.Event().wait()
        finally:
            cleaned.set()
            await respond(send)

    with pytest.raises(RuntimeError, match="Total request timeout exceeded"):
        await transport.run(RequestTimeoutASGIMiddleware(stream, total_timeout=0.01))

    await asyncio.wait_for(cleaned.wait(), 1)
    assert len(transport.sent) == 2
    assert transport.sent[0]["status"] == 200
    assert transport.sent[-1]["more_body"] is True


RECEIVE_DEADLINE_CASES: list[tuple[list[Message], str]] = [
    ([], "Request first body timeout exceeded."),
    (
        [{"type": "http.request", "body": b"a", "more_body": True}],
        "Request chunk timeout exceeded.",
    ),
]


@pytest.mark.parametrize(("messages", "detail"), RECEIVE_DEADLINE_CASES)
async def test_receive_deadlines(messages: list[Message], detail: str) -> None:
    cleaned = asyncio.Event()

    async def read(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            while True:
                await receive()
        finally:
            cleaned.set()

    transport = Transport(messages)

    await transport.run(
        RequestTimeoutASGIMiddleware(read, first_body_timeout=0.01, chunk_timeout=0.01)
    )
    await asyncio.wait_for(cleaned.wait(), 1)
    assert_timeout(transport, detail)


async def test_completed_body_does_not_apply_chunk_timeout_to_disconnect_wait() -> None:
    transport = Transport([{"type": "http.request", "body": b"payload"}])

    async def read(scope: Scope, receive: Receive, send: Send) -> None:
        assert (await receive())["body"] == b"payload"
        await receive()  # Wait for disconnect, not another upload chunk.

    await transport.run(
        RequestTimeoutASGIMiddleware(read, chunk_timeout=0.001, total_timeout=0.03)
    )
    assert_timeout(transport, "Total request timeout exceeded.")


async def test_disconnect_cancels_handler_that_never_reads_body() -> None:
    started = asyncio.Event()
    cleaned = asyncio.Event()
    transport = Transport([{"type": "http.request", "body": b""}])

    async def slow(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaned.set()
            await respond(send)

    task = asyncio.create_task(transport.run(RequestTimeoutASGIMiddleware(slow)))

    await asyncio.wait_for(started.wait(), 1)
    transport.incoming.put_nowait({"type": "http.disconnect"})
    await task
    await asyncio.wait_for(cleaned.wait(), 1)
    assert transport.sent == []


async def test_external_cancellation_propagates_without_408() -> None:
    started = asyncio.Event()
    cleaned = asyncio.Event()
    transport = Transport()

    async def slow(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    task = asyncio.create_task(transport.run(RequestTimeoutASGIMiddleware(slow)))

    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.wait_for(cleaned.wait(), 1)
    assert transport.sent == []


async def test_cancellation_resistant_late_work_is_observed_without_late_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()
    logger = Mock()

    monkeypatch.setattr("app.common.middleware.request_timeout.log", logger)
    transport = Transport()

    async def stubborn(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            await respond(send)

            raise ValueError("sensitive dependency detail") from None

    middleware = RequestTimeoutASGIMiddleware(stubborn, total_timeout=0.01)

    try:
        await transport.run(middleware)
        assert_timeout(transport, "Total request timeout exceeded.")
    finally:
        release.set()
        # Let the retained work and its observation callback settle.
        for _ in range(10):
            await asyncio.sleep(0)
            if logger.error.called:
                break

    logger.error.assert_called_once()
    assert (
        logger.error.call_args.args[0]
        == "Request work failed after its response closed."
    )
    assert isinstance(logger.error.call_args.kwargs["error"], ValueError)
    assert len(transport.sent) == 2


async def test_receive_owner_preserves_body_chunks() -> None:
    delivered: list[bytes] = []
    messages: list[Message] = [
        {"type": "http.request", "body": bytes([index]), "more_body": index < 3}
        for index in range(4)
    ]
    transport = Transport(messages)

    async def read(scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()

            delivered.append(message["body"])
            if not message.get("more_body", False):
                break

        await respond(send)

    await transport.run(RequestTimeoutASGIMiddleware(read))
    assert delivered == [b"\x00", b"\x01", b"\x02", b"\x03"]
    assert transport.sent[0]["status"] == 200


async def test_non_http_scope_is_forwarded_unchanged() -> None:
    calls: list[Scope] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append(scope)

    scope: Scope = {"type": "lifespan"}
    transport = Transport()

    await RequestTimeoutASGIMiddleware(downstream)(
        scope, transport.receive, transport.send
    )
    assert calls == [scope]


@pytest.mark.parametrize(
    "name", ["first_body_timeout", "chunk_timeout", "total_timeout"]
)
@pytest.mark.parametrize("value", [0, float("nan"), float("inf")])
def test_invalid_budgets_fail_at_configuration(name: str, value: float) -> None:
    with pytest.raises(ValueError, match=name):
        RequestTimeoutASGIMiddleware(respond, **{name: value})  # type: ignore[arg-type]


@pytest.mark.parametrize("failure_at", ["receive", "send"])
async def test_transport_disconnect_errors_do_not_create_an_error_response(
    failure_at: str,
) -> None:
    cleaned = asyncio.Event()
    transport = Transport()

    async def receive() -> Message:
        if failure_at == "receive":
            raise OSError("connection closed")

        return await transport.receive()

    async def send(message: Message) -> None:
        raise OSError("connection closed")

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            if failure_at == "send":
                await respond(send)
            else:
                await asyncio.Event().wait()
        finally:
            cleaned.set()

    await asyncio.wait_for(
        RequestTimeoutASGIMiddleware(downstream)(SCOPE, receive, send), 1
    )
    await asyncio.wait_for(cleaned.wait(), 1)
    assert transport.sent == []


@pytest.mark.parametrize("failure_at", ["receive", "send"])
async def test_unexpected_server_timeout_is_preserved(failure_at: str) -> None:
    cleaned = asyncio.Event()
    error = TimeoutError("server operation failed")

    async def receive() -> Message:
        if failure_at == "receive":
            raise error

        return await asyncio.Queue[Message]().get()

    async def send(message: Message) -> None:
        raise error

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            if failure_at == "send":
                await respond(send)
            else:
                await asyncio.Event().wait()
        finally:
            cleaned.set()

    transport = Transport()

    with pytest.raises(TimeoutError) as caught:
        await RequestTimeoutASGIMiddleware(downstream)(SCOPE, receive, send)

    assert caught.value is error
    await asyncio.wait_for(cleaned.wait(), 1)
    assert transport.sent == []


async def test_ignored_upload_is_not_drained_into_unbounded_memory() -> None:
    prefetched = asyncio.Event()
    release = asyncio.Event()
    read_count = 0
    transport = Transport()

    async def receive() -> Message:
        nonlocal read_count
        read_count += 1

        if read_count == 2:
            prefetched.set()

        return {"type": "http.request", "body": b"chunk", "more_body": True}

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        await release.wait()
        await respond(send)

    task = asyncio.create_task(
        RequestTimeoutASGIMiddleware(downstream)(SCOPE, receive, transport.send)
    )

    try:
        await asyncio.wait_for(prefetched.wait(), 1)
        await asyncio.sleep(0)
        assert read_count == 2
    finally:
        release.set()
        await asyncio.wait_for(task, 1)
