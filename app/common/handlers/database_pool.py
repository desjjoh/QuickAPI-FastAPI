"""Bounded admission around SQLAlchemy's native asynchronous connection pool."""

import asyncio
from collections import deque
from typing import Any, cast

from sqlalchemy.pool import AsyncAdaptedQueuePool, ConnectionPoolEntry
from sqlalchemy.util.concurrency import await_only, greenlet_spawn
from starlette.exceptions import HTTPException


class DatabaseUnavailableError(HTTPException):
    def __init__(self, code: str) -> None:
        super().__init__(503, "Database temporarily unavailable.")
        self.code = code


class Admission:
    def __init__(self, limit: int, queue_limit: int) -> None:
        self.limit = limit
        self.queue_limit = queue_limit
        self.active = 0
        self.waiters: deque[asyncio.Future[None]] = deque()
        self.closed = False

    async def acquire(self) -> None:
        if self.closed:
            raise DatabaseUnavailableError("DB_POOL_CLOSED")
        if self.active < self.limit:
            self.active += 1
            return
        if len(self.waiters) >= self.queue_limit:
            raise DatabaseUnavailableError("DB_POOL_CAPACITY")
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.waiters.append(waiter)
        try:
            await waiter
        except BaseException:
            if waiter in self.waiters:
                self.waiters.remove(waiter)
            elif not waiter.cancelled() and waiter.exception() is None:
                self.release()
            raise

    def release(self) -> None:
        while self.waiters:
            waiter = self.waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)
                return
        self.active -= 1

    def close(self) -> None:
        self.closed = True
        while self.waiters:
            waiter = self.waiters.popleft()
            if not waiter.done():
                waiter.set_exception(DatabaseUnavailableError("DB_POOL_CLOSED"))


class BoundedAsyncPool(AsyncAdaptedQueuePool):
    """Pool extension hooks are isolated here and covered by socket/SQL tests."""

    policy_queue_limit = 50
    policy_acquire_timeout = 1.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.admission = Admission(self.size(), self.policy_queue_limit)
        self.acquire_timeout = self.policy_acquire_timeout
        self._leased: set[ConnectionPoolEntry] = set()

    def _do_get(self) -> ConnectionPoolEntry:
        return await_only(self._acquire_record())

    async def _acquire_record(self) -> ConnectionPoolEntry:
        acquired = False
        try:
            async with asyncio.timeout(self.acquire_timeout):
                await self.admission.acquire()
                acquired = True
                record = await greenlet_spawn(super()._do_get)
                if self.admission.closed:
                    await greenlet_spawn(record.close)
                    raise DatabaseUnavailableError("DB_POOL_CLOSED")
                self._leased.add(record)
                return record
        except TimeoutError:
            if acquired:
                self.admission.release()
            raise DatabaseUnavailableError("DB_POOL_ACQUIRE_TIMEOUT") from None
        except BaseException:
            if acquired:
                self.admission.release()
            raise

    def _do_return_conn(self, record: ConnectionPoolEntry) -> None:
        try:
            if self.admission.closed:
                record.close()
            else:
                super()._do_return_conn(record)
        finally:
            if record in self._leased:
                self._leased.remove(record)
                self.admission.release()

    def dispose(self) -> None:
        self.admission.close()
        super().dispose()

    def recreate(self) -> "BoundedAsyncPool":
        pool = cast(BoundedAsyncPool, super().recreate())
        pool.admission = Admission(self.size(), self.admission.queue_limit)
        pool.acquire_timeout = self.acquire_timeout
        return pool
