import asyncio
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

import anyio
import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse

from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware
from app.config.application import create_app

pytestmark = pytest.mark.integration


@asynccontextmanager
async def running(
    app: FastAPI, protocol: Literal["h11", "httptools"]
) -> AsyncGenerator[int, None]:
    listener = socket.socket()

    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    port = listener.getsockname()[1]
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        http=protocol,
        ws="none",
        loop="asyncio",
        lifespan="off",
        access_log=False,
        proxy_headers=False,
        log_config=None,
        timeout_graceful_shutdown=1,
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[listener]))

    try:
        async with asyncio.timeout(3):
            while not server.started:
                if task.done():
                    await task

                    raise RuntimeError("Test server failed to start")

                await asyncio.sleep(0.001)

        yield port
    finally:
        server.should_exit = True

        try:
            await asyncio.wait_for(task, 3)
        finally:
            listener.close()


def application(total_timeout: float = 0.15) -> FastAPI:
    app = create_app()

    for middleware in app.user_middleware:
        if middleware.cls is RequestTimeoutASGIMiddleware:
            middleware.kwargs.update(
                total_timeout=total_timeout,
                first_body_timeout=0.1,
                chunk_timeout=0.05,
            )

    return app


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_408_precedes_slow_cleanup_and_suppresses_late_response(
    protocol: Literal["h11", "httptools"],
) -> None:
    app = application()
    release = asyncio.Event()
    cleaned = asyncio.Event()

    @app.get("/slow")
    async def slow() -> dict[str, bool]:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            cleaned.set()

        return {"unexpected": True}

    async with running(app, protocol) as port:
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
                response = await client.get("/slow", timeout=2)

                assert response.status_code == 408
                assert response.json()["message"] == "Total request timeout exceeded."
                assert response.headers["x-request-id"]
                assert response.headers["x-frame-options"] == "DENY"
                assert not cleaned.is_set()
                release.set()
                await asyncio.wait_for(cleaned.wait(), 1)
                # Successful work on the next request proves late output did not
                # corrupt the HTTP connection after the middleware sent 408.
                following = await client.get("/")

                assert following.status_code == 200
        finally:
            release.set()
            await asyncio.wait_for(cleaned.wait(), 1)


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_stream_is_truncated_before_async_cleanup_finishes(
    protocol: Literal["h11", "httptools"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import UUID

    # Status-like digits in correlation headers must not look like a second response.
    monkeypatch.setattr(
        "app.common.middleware.request_context.uuid.uuid4",
        lambda: UUID("408500ab-0000-0000-0000-000000000000"),
    )
    app = application()
    cleaning = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()

    async def chunks() -> AsyncGenerator[bytes, None]:
        try:
            yield b"partial"
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            # Starlette streams use an AnyIO cancel scope. Resource-owned async
            # cleanup must shield its awaits from that already-cancelled scope.
            with anyio.CancelScope(shield=True):
                await release.wait()
                cleaned.set()

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(chunks())

    async with running(app, protocol) as port:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            writer.write(
                b"GET /stream HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            )
            await writer.drain()
            wire = await asyncio.wait_for(reader.read(), 2)

            assert wire.count(b"HTTP/1.1") == 1
            assert wire.split(b"\r\n", 1)[0] == b"HTTP/1.1 200 OK"
            assert b"partial" in wire
            assert b"x-request-id: 408500ab\r\n" in wire
            assert not wire.endswith(b"0\r\n\r\n")
            await asyncio.wait_for(cleaning.wait(), 1)
            assert not cleaned.is_set()
        finally:
            release.set()
            await asyncio.wait_for(cleaned.wait(), 1)
            writer.close()
            await writer.wait_closed()


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_disconnect_cancels_handler_without_body_reads(
    protocol: Literal["h11", "httptools"],
) -> None:
    app = application(total_timeout=5)
    started = asyncio.Event()
    cleaned = asyncio.Event()

    @app.get("/wait")
    async def wait() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async with running(app, protocol) as port:
        _, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            writer.write(b"GET /wait HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            await asyncio.wait_for(started.wait(), 1)
        finally:
            writer.close()
            await writer.wait_closed()

        # The total deadline is five seconds; cleanup must come from disconnect.
        await asyncio.wait_for(cleaned.wait(), 1)


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_stalled_body_uses_json_408_not_parser_400(
    protocol: Literal["h11", "httptools"],
) -> None:
    app = application(total_timeout=1)

    @app.post("/body")
    async def body(request: Request) -> dict[str, object]:
        return {"body": await request.json()}

    async with running(app, protocol) as port:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            writer.write(
                b"POST /body HTTP/1.1\r\nHost: localhost\r\n"
                b"Content-Type: application/json\r\nContent-Length: 10\r\n"
                b"Connection: close\r\n\r\n{"
            )
            await writer.drain()
            wire = await asyncio.wait_for(reader.read(), 2)

            assert wire.count(b"HTTP/1.1") == 1
            assert b"408 Request Timeout" in wire
            assert b'"message":"Request chunk timeout exceeded."' in wire
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_completed_request_deadline_cannot_affect_reused_socket(
    protocol: Literal["h11", "httptools"],
) -> None:
    app = application()

    async with running(app, protocol) as port:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            for _ in range(3):
                writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                await writer.drain()
                headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 1)

                assert headers.startswith(b"HTTP/1.1 200 OK")
                length = next(
                    int(line.split(b":", 1)[1])
                    for line in headers.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                body = await asyncio.wait_for(reader.readexactly(length), 1)

                assert b"Hello World" in body
                await asyncio.sleep(0.2)
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_disconnect_closes_stream_generator(
    protocol: Literal["h11", "httptools"],
) -> None:
    app = application(total_timeout=5)
    cleaned = asyncio.Event()

    async def chunks() -> AsyncGenerator[bytes, None]:
        try:
            yield b"partial"
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(chunks())

    async with running(app, protocol) as port:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            writer.write(b"GET /stream HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            await asyncio.wait_for(reader.readuntil(b"partial\r\n"), 1)
        finally:
            writer.close()
            await writer.wait_closed()

        await asyncio.wait_for(cleaned.wait(), 1)
