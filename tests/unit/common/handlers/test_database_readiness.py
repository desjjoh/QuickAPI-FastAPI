import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.common.handlers.database_readiness import DatabaseReadiness

pytestmark = pytest.mark.unit


async def test_shared_probe_survives_caller_cancellation_and_caches() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    @asynccontextmanager
    async def connect() -> AsyncGenerator[SimpleNamespace, None]:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        yield SimpleNamespace(execute=AsyncMock())

    probe = DatabaseReadiness(cast(AsyncEngine, SimpleNamespace(connect=connect)))
    assert await probe.check() is False
    probe.resume()
    caller = asyncio.create_task(probe.check())
    await entered.wait()
    others = [asyncio.create_task(probe.check()) for _ in range(20)]
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    release.set()
    assert all(await asyncio.gather(*others))
    assert await probe.check() is True and calls == 1
    await probe.stop()
    assert await probe.check() is False


async def test_failed_cache_expires_and_resume_discards_it() -> None:
    calls = 0

    @asynccontextmanager
    async def connect() -> AsyncGenerator[SimpleNamespace, None]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("private connection details")
        yield SimpleNamespace(execute=AsyncMock())

    probe = DatabaseReadiness(
        cast(AsyncEngine, SimpleNamespace(connect=connect)), cache_ms=20
    )
    probe.resume()
    assert await probe.check() is False
    assert await probe.check() is False and calls == 1
    await asyncio.sleep(0.03)
    assert await probe.check() is True and calls == 2
    probe.resume()
    assert await probe.check() is True and calls == 3
    await probe.stop()


@pytest.mark.parametrize("stop", [False, True])
async def test_timeout_and_stop_retire_only_owned_connection(stop: bool) -> None:
    entered = asyncio.Event()

    async def execute(_: object) -> None:
        entered.set()
        await asyncio.Event().wait()

    invalidate = AsyncMock()

    @asynccontextmanager
    async def connect() -> AsyncGenerator[SimpleNamespace, None]:
        yield SimpleNamespace(execute=execute, invalidate=invalidate)

    probe = DatabaseReadiness(
        cast(AsyncEngine, SimpleNamespace(connect=connect)), timeout_ms=30
    )
    probe.resume()
    task = asyncio.create_task(probe.check())
    await entered.wait()
    if stop:
        await probe.stop()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert await task is False
    invalidate.assert_awaited_once()
    await probe.stop()


@pytest.mark.parametrize("timeout,cache", [(0, 1), (1, -1)])
def test_invalid_policy(timeout: int, cache: int) -> None:
    with pytest.raises(ValueError):
        DatabaseReadiness(cast(AsyncEngine, object()), timeout, cache)
