import asyncio
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.services import idempotency_cleanup_service as module
from app.common.services.idempotency_cleanup_service import IdempotencyCleanupService

pytestmark = pytest.mark.unit


async def test_overlapping_sweeps_share_work_and_stop_waits_for_active_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reached, release = asyncio.Event(), asyncio.Event()
    calls: list[int] = []

    async def purge(session: AsyncSession, limit: int) -> int:
        assert session.in_transaction()
        calls.append(limit)
        reached.set()
        await release.wait()

        return limit

    monkeypatch.setattr(module.idempotency_repo, 'purge_expired_batch', purge)
    service = IdempotencyCleanupService()

    await service.start()
    await service.start()
    first = asyncio.create_task(service.sweep())
    second = asyncio.create_task(service.sweep())
    stopped: asyncio.Task[None] | None = None

    try:
        await asyncio.wait_for(reached.wait(), 1)
        assert await service.check()
        service.quiesce()
        stopped = asyncio.create_task(service.stop())

        await asyncio.sleep(0)
        assert not stopped.done()
        release.set()
        assert await first == await second == calls[0]
        await stopped
        assert len(calls) == 1
        assert not await service.check()
        assert await service.sweep() == 0
    finally:
        release.set()
        await asyncio.gather(first, second, return_exceptions=True)
        await service.stop()


async def test_scheduled_cleanup_logs_failures_and_can_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged = asyncio.Event()

    async def purge(session: AsyncSession, limit: int) -> int:
        raise RuntimeError('Cleanup failure')

    logger = Mock()

    def record_error(*args: Any, **kwargs: Any) -> None:
        logged.set()

    logger.error.side_effect = record_error

    monkeypatch.setattr(module, 'log', logger)
    monkeypatch.setattr(module, 'CLEANUP_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(module.idempotency_repo, 'purge_expired_batch', purge)
    service = IdempotencyCleanupService()

    try:
        await service.start()
        await asyncio.wait_for(logged.wait(), 1)
        await service.stop()
        logger.error.assert_called_once()
        assert logger.error.call_args.args == ('Idempotency response cleanup failed.',)
        assert isinstance(logger.error.call_args.kwargs['error'], RuntimeError)
        await service.start()
        assert await service.check()
    finally:
        await service.stop()
