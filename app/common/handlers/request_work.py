"""Application-owned admission and work lifetime, independent of response lifetime."""

import asyncio
import time
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app.common.models.error_model import error_response


class RequestWork:
    def __init__(self, drain_seconds: float) -> None:
        self.drain_seconds = drain_seconds
        self.draining_at: float | None = None
        self.failed = False
        self.tasks: set[asyncio.Task[Any]] = set()

    def resume(self) -> None:
        if any(not task.done() for task in self.tasks):
            raise RuntimeError('Cannot resume while previous request work is active.')
        self.tasks.clear()
        self.draining_at = None
        self.failed = False

    def quiesce(self) -> None:
        if self.draining_at is None:
            self.draining_at = time.monotonic()

    def track(self, task: asyncio.Task[Any]) -> None:
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def remaining(self) -> float:
        if self.draining_at is None:
            return self.drain_seconds
        return max(0.0, self.drain_seconds - (time.monotonic() - self.draining_at))

    async def drain(self) -> None:
        self.quiesce()
        while pending := {task for task in self.tasks if not task.done()}:
            _, unfinished = await asyncio.wait(pending, timeout=self.remaining())
            if unfinished:
                self.failed = True
                for task in unfinished:
                    task.cancel()
                # Keep dependencies alive for cancellation/rollback cleanup. The
                # entrypoint's independent final watchdog bounds uncooperative work.
                await asyncio.gather(*unfinished, return_exceptions=True)
                return


class RequestAdmission:
    def __init__(self, app: ASGIApp, work: RequestWork) -> None:
        self.app, self.work = app, work

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        if self.work.draining_at is not None:
            response = error_response(
                status=503, message='Application is shutting down.'
            )
            response.headers['Connection'] = 'close'
            await response(scope, receive, send)
            return
        task = asyncio.current_task()
        assert task is not None
        self.work.track(task)
        try:
            await self.app(scope, receive, send)
        finally:
            self.work.tasks.discard(task)
