"""Narrow Uvicorn integration: quiesce before transport drain and bound process exit."""

import asyncio
import os
import signal
import socket
import threading
from collections.abc import Generator
from contextlib import contextmanager
from types import FrameType
from typing import Any, cast

import uvicorn
from uvicorn.server import HANDLED_SIGNALS

from app.config.environment import settings
from app.config.logging import log


class ApplicationServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        self._watchdog: threading.Timer | None = None

    @contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        # Own signal exit semantics: successful cleanup returns zero, allowing
        # Runner cleanup to finish before the final success record is emitted.
        if threading.current_thread() is not threading.main_thread():
            yield

            return

        previous = {
            sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS
        }

        try:
            yield
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    def _application(self) -> Any:
        application: Any = cast(Any, self.config).loaded_app

        while not hasattr(application, 'state'):
            application = application.app

        return application

    def _begin_shutdown(self, reason: str = 'Shutdown requested') -> None:
        # Also covers a blocked event loop and asyncio runner's final task cleanup.
        if self._watchdog is None:
            self._watchdog = threading.Timer(
                settings.SHUTDOWN_TIMEOUT_MS / 1000, self._force_exit
            )
            self._watchdog.daemon = True

            self._watchdog.start()
            log.warning(f'{reason} — initiating shutdown')

        if self.config.loaded:
            app = self._application()
            app.state.shutdown_notice_logged = True

            app.state.lifecycle.quiesce()
            app.state.request_work.quiesce()

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        # Uvicorn returns before shutdown() when a signal arrives during startup.
        # Close any listener/resources that completed startup after that signal.
        if self.should_exit and self.started:
            await self.shutdown(sockets)
        elif self.started:
            port = self.config.port

            log.info(f'HTTP server running on port {port} — http://localhost:{port}')

    @staticmethod
    def _force_exit(
        diagnostic: bytes = b'Final shutdown deadline exceeded; unfinished work may have an unknown outcome.\n',
    ) -> None:
        try:
            os.write(2, diagnostic)
        finally:
            # Diagnostic output is best effort. A closed/broken stderr must not
            # defeat the final process deadline or repeated-signal termination.
            os._exit(1)

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        if self._watchdog is not None:
            self._force_exit(b'Repeated shutdown signal; forcing termination.\n')

        self._begin_shutdown(f'{signal.Signals(sig).name} received')
        super().handle_exit(sig, frame)

    def request_shutdown(self) -> None:
        """Graceful programmatic stop; unlike Windows terminate(), this drains."""
        if self._watchdog is not None:
            self._force_exit()

        self._begin_shutdown()
        self.should_exit = True

    async def _wait_tasks_to_complete(self) -> None:
        work = self._application().state.request_work

        try:
            async with asyncio.timeout(work.remaining()):
                await super()._wait_tasks_to_complete()
                await work.drain()
        except (asyncio.CancelledError, TimeoutError):
            work.failed = True

            raise

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self._begin_shutdown()
        work = self._application().state.request_work
        self.config.timeout_graceful_shutdown = work.remaining()

        await super().shutdown(sockets)
        if work.failed or self._application().state.lifecycle.shutdown_failed:
            log.error(
                'Shutdown did not complete cleanly; unfinished work may have an unknown outcome.'
            )

            raise RuntimeError('Application shutdown failed.')

    def run(self, sockets: list[socket.socket] | None = None) -> None:
        try:
            super().run(sockets)
            if not self.started:
                raise RuntimeError('HTTP server did not start.')

            log.info('Application exited (code 0)')
        finally:
            if self._watchdog is not None:
                self._watchdog.cancel()
