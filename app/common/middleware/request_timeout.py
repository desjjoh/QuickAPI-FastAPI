from __future__ import annotations

import asyncio
import math
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.request_activity import RequestExpired, request_activity
from app.common.handlers.request_work import RequestWork
from app.common.middleware.request_outcome import abort_request
from app.common.models.error_model import error_response
from app.config.logging import log


class _StreamDeadlineExceededError(RuntimeError):
    """Let the ASGI server abort a response whose headers are already on the wire."""


class RequestTimeoutASGIMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        first_body_timeout: float = 5.0,
        chunk_timeout: float = 2.0,
        total_timeout: float = 10.0,
        work: RequestWork | None = None,
    ) -> None:
        for name, value in (
            ("first_body_timeout", first_body_timeout),
            ("chunk_timeout", chunk_timeout),
            ("total_timeout", total_timeout),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")
        self.app = app
        self.first_body_timeout = first_body_timeout
        self.chunk_timeout = chunk_timeout
        self.total_timeout = total_timeout
        self.work = work
        # Cancellation is cooperative. Retain work until it settles even when the
        # transport must finish first; retrieve late failures in its done callback.
        self._pending: set[asyncio.Task[None]] = set()

    def track_work(self, task: asyncio.Task[None]) -> None:
        if self.work is not None:
            self.work.track(task)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = _RequestDeadline(self, scope, receive, send)
        await request.run()


class _RequestDeadline:
    def __init__(
        self,
        middleware: RequestTimeoutASGIMiddleware,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        self.middleware = middleware
        self.scope = scope
        self.receive = receive
        self.send = send
        self.incoming: asyncio.Queue[Message] = asyncio.Queue(maxsize=1)
        self.interrupted = asyncio.Event()
        self.completed = asyncio.Event()
        self.started = False
        self.closed = False
        self.disconnected = False
        self.body_started = False
        self.body_complete = False
        self.timeout_detail: str | None = None
        self.activity = request_activity(scope)
        self.activity.expires_at = min(
            self.activity.expires_at, time.monotonic() + middleware.total_timeout
        )

    async def read_messages(self) -> None:
        # Exactly one owner reads the server channel. Backpressure bounds this to
        # one queued message and one in-flight message, never an entire upload.
        try:
            while True:
                message = await self.receive()
                if message["type"] == "http.disconnect":
                    if not self.completed.is_set():
                        self.disconnected = True
                        self.activity.abandon('Request disconnected.')
                        self.interrupted.set()
                    return
                await self.incoming.put(message)
        except TimeoutError:
            raise  # TimeoutError is also an OSError; it is not proof of disconnect.
        except OSError:
            self.disconnected = True
            self.activity.abandon('Request disconnected.')
            self.interrupted.set()

    async def receive_body(self) -> Message:
        if self.closed or self.disconnected:
            return {"type": "http.disconnect"}
        if self.body_complete:
            await self.interrupted.wait()
            return {"type": "http.disconnect"}
        budget = (
            self.middleware.chunk_timeout
            if self.body_started
            else self.middleware.first_body_timeout
        )
        try:
            async with asyncio.timeout(budget):
                message = await self.incoming.get()
        except TimeoutError:
            self.timeout_detail = (
                "Request chunk timeout exceeded."
                if self.body_started
                else "Request first body timeout exceeded."
            )
            self.activity.abandon(self.timeout_detail)
            self.interrupted.set()
            # Do not let FastAPI's request parser convert this into a JSON 400.
            # The request owner, rather than downstream exception handling, emits 408.
            raise asyncio.CancelledError from None
        self.body_started = True
        self.body_complete = not message.get("more_body", False)
        return message

    async def send_response(self, message: Message) -> None:
        if self.closed or self.disconnected or self.completed.is_set():
            return
        if message["type"] == "http.response.start":
            self.started = True
        try:
            await self.send(message)
        except TimeoutError:
            raise
        except OSError:
            self.disconnected = True
            self.activity.abandon('Request disconnected.')
            self.interrupted.set()
            raise
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            self.completed.set()

    def observe_work(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            error = task.exception()
            if (
                error is not None
                and self.closed
                and not isinstance(error, RequestExpired)
            ):
                log.error(
                    "Request work failed after its response closed.",
                    error=error,
                )

    async def run_app(self) -> None:
        await self.middleware.app(self.scope, self.receive_body, self.send_response)

    async def run(self) -> None:
        work = asyncio.create_task(self.run_app())
        self.middleware.track_work(work)
        work.add_done_callback(self.observe_work)
        reader = asyncio.create_task(self.read_messages())
        interrupted = asyncio.create_task(self.interrupted.wait())
        completed = asyncio.create_task(self.completed.wait())
        watchers = (reader, interrupted, completed)
        try:
            done, _ = await asyncio.wait(
                (work, *watchers),
                timeout=self.middleware.total_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self.completed.is_set():
                # A finished response cannot expire during dependency/background cleanup.
                await work
            elif self.disconnected:
                abort_request(self.scope)
                self.closed = True
                if not self.activity.owns_mutation:
                    work.cancel()
            elif self.timeout_detail is not None or not done:
                self.closed = True
                detail = self.timeout_detail or "Total request timeout exceeded."
                self.activity.abandon(detail)
                if not self.activity.owns_mutation:
                    work.cancel()
                if self.started:
                    abort_request(self.scope)
                    # ASGI has no portable socket-abort message. Raising after
                    # response.start lets Uvicorn close the incomplete response.
                    raise _StreamDeadlineExceededError(detail)
                response = error_response(status=408, message=detail)
                await response(self.scope, self.receive_body, self.send)
            else:
                if reader in done:
                    await reader  # Preserve unexpected receive failures.
                await work  # Preserve downstream errors, including TimeoutError.
        finally:
            self.closed = True
            if not work.done():
                self.activity.abandon('Request interrupted.')
            if (
                not work.done()
                and not work.cancelling()
                and not self.activity.owns_mutation
            ):
                work.cancel()
            for task in watchers:
                task.cancel()
            await asyncio.gather(*watchers, return_exceptions=True)
