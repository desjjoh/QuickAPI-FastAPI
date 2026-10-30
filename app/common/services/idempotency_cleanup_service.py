"""Lifecycle-owned, bounded cleanup shared by all idempotent domains."""

import asyncio

from app.common.models.idempotency_model import CLEANUP_INTERVAL_SECONDS
from app.config import database
from app.config.environment import settings
from app.config.logging import log
from app.database.repositories.idempotency_repo import idempotency_repo


class IdempotencyCleanupService:
    name = 'idempotency cleanup'

    def __init__(self) -> None:
        self._accepting = False
        self._stop = asyncio.Event()
        self._timer: asyncio.Task[None] | None = None
        self._pending: asyncio.Task[int] | None = None

    async def start(self) -> None:
        if self._accepting:
            return

        self._accepting = True

        self._stop.clear()
        self._timer = asyncio.create_task(self._run())

    def quiesce(self) -> None:
        self._accepting = False

        self._stop.set()

    async def stop(self) -> None:
        self.quiesce()
        if self._timer is not None:
            await self._timer
            self._timer = None

        if self._pending is not None:
            await asyncio.shield(self._pending)

    async def check(self) -> bool:
        return self._accepting and self._timer is not None and not self._timer.done()

    async def _run(self) -> None:
        while self._accepting:
            try:
                await asyncio.wait_for(self._stop.wait(), CLEANUP_INTERVAL_SECONDS)
            except TimeoutError:
                try:
                    await self.sweep()
                except Exception as exc:
                    log.error('Idempotency response cleanup failed.', error=exc)

    async def sweep(self) -> int:
        if self._pending is None:
            if not self._accepting:
                return 0

            self._pending = asyncio.create_task(self._sweep())

        pending = self._pending

        try:
            return await asyncio.shield(pending)
        finally:
            if pending.done() and self._pending is pending:
                self._pending = None

    async def _sweep(self) -> int:
        count = 0

        for _ in range(settings.IDEMPOTENCY_CLEANUP_MAX_BATCHES):
            if not self._accepting:
                break

            async with (
                database.SessionLocal(autobegin=False) as session,
                session.begin(),
            ):
                removed = await idempotency_repo.purge_expired_batch(
                    session, settings.IDEMPOTENCY_CLEANUP_BATCH_SIZE
                )

            count += removed

            if removed < settings.IDEMPOTENCY_CLEANUP_BATCH_SIZE:
                break

        return count
