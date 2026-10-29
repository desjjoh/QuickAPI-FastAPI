"""On-demand database probes with shared ownership and bounded SQL work."""

import asyncio
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class DatabaseReadiness:
    def __init__(
        self, engine: AsyncEngine, timeout_ms: int = 1000, cache_ms: int = 1000
    ) -> None:
        if timeout_ms <= 0 or cache_ms < 0:
            raise ValueError("Invalid database readiness policy.")
        self.engine = engine
        self.timeout = timeout_ms / 1000
        self.cache = cache_ms / 1000
        self._active: asyncio.Task[bool] | None = None
        self._cached: tuple[bool, float] | None = None
        self._stopped = True

    def resume(self) -> None:
        self._stopped = False
        self._cached = None

    async def check(self) -> bool:
        if self._stopped:
            return False
        if self._active is not None:
            return await asyncio.shield(self._active)
        if self._cached is not None and time.monotonic() < self._cached[1]:
            return self._cached[0]
        task = asyncio.create_task(self._probe(), name="database-readiness")
        self._active = task
        task.add_done_callback(self._finished)
        return await asyncio.shield(task)

    def _finished(self, task: asyncio.Task[bool]) -> None:
        if self._active is task:
            self._active = None
        if not task.cancelled():
            healthy = task.result()
            if not self._stopped:
                self._cached = (healthy, time.monotonic() + self.cache)

    async def _probe(self) -> bool:
        try:
            async with asyncio.timeout(self.timeout):
                async with self.engine.connect() as connection:
                    try:
                        await connection.execute(text("SELECT 1"))
                    except BaseException:
                        # Only this probe's lease is retired. Never dispose the
                        # shared engine to recover from a runtime probe failure.
                        await connection.invalidate()
                        raise
            return True
        except Exception:
            return False

    async def stop(self) -> None:
        self._stopped = True
        self._cached = None
        task = self._active
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._active = None
