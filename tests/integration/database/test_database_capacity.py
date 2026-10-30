import asyncio
import importlib
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.common.handlers.database_pool import BoundedAsyncPool, DatabaseUnavailableError
from app.common.handlers.exception_handler import http_exception_handler
from app.config.database_transport import DatabasePolicy, build_database_engine

pytestmark = pytest.mark.integration


async def test_connection_finishing_after_disposal_is_closed_not_delivered(
    database_engine: AsyncEngine,
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    started, release = asyncio.Event(), asyncio.Event()
    identifiers: list[int] = []
    driver = importlib.import_module("asyncmy")
    _, arguments = database_engine.dialect.create_connect_args(database_engine.url)

    async def creator() -> Any:
        started.set()
        await release.wait()
        connection: Any = await driver.connect(**arguments)

        async with connection.cursor() as cursor:
            await cursor.execute("SELECT CONNECTION_ID()")
            row = await cursor.fetchone()

            identifiers.append(int(row[0]))

        return connection

    engine = create_async_engine(
        database_engine.url,
        async_creator=creator,
        poolclass=BoundedAsyncPool,
        pool_size=1,
        max_overflow=0,
    )
    pool = engine.pool

    assert isinstance(pool, BoundedAsyncPool)

    async def connect() -> None:
        async with engine.connect():
            pytest.fail("A disposed pool must not deliver a late connection")

    task = asyncio.create_task(connect())

    try:
        await asyncio.wait_for(started.wait(), 2)
        await engine.dispose()
        release.set()
        with pytest.raises(DatabaseUnavailableError) as error:
            await task

        assert error.value.code == "DB_POOL_CLOSED" and pool.admission.active == 0
        async with asyncio.timeout(3):
            while True:
                async with database_engine.connect() as control:
                    rows = (
                        (await control.execute(text("SHOW PROCESSLIST")))
                        .mappings()
                        .all()
                    )

                if not any(int(row["Id"]) in identifiers for row in rows):
                    break

                await asyncio.sleep(0.01)
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await engine.dispose()


async def wait_for_waiters(pool: BoundedAsyncPool, count: int) -> None:
    async with asyncio.timeout(2):
        while len(pool.admission.waiters) != count:
            await asyncio.sleep(0.001)


async def test_real_pool_limits_queue_timeout_cancel_and_recovery(
    database_engine: AsyncEngine,
) -> None:
    policy = DatabasePolicy(connection_limit=1, queue_limit=1, acquire_timeout_ms=100)
    engine = build_database_engine(database_engine.url, policy=policy)

    assert isinstance(engine.pool, BoundedAsyncPool)
    pool = engine.pool

    try:
        held = await engine.connect()

        async def acquire() -> None:
            async with engine.connect() as connection:
                await connection.execute(text('SELECT 1'))

        waiter = asyncio.create_task(acquire())

        await wait_for_waiters(pool, 1)
        with pytest.raises(DatabaseUnavailableError) as full:
            await engine.connect()

        assert full.value.code == 'DB_POOL_CAPACITY'
        from starlette.exceptions import HTTPException

        app = FastAPI()

        app.exception_handler(HTTPException)(http_exception_handler)
        factory = async_sessionmaker(engine)

        @app.get('/')
        async def query() -> None:
            async with factory() as session:
                await session.execute(text('SELECT 1'))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app, raise_app_exceptions=False),
            base_url='http://test',
        ) as client:
            rejected = await client.get('/')

        assert rejected.status_code == 503
        assert rejected.json()['message'] == 'Database temporarily unavailable.'
        with pytest.raises(DatabaseUnavailableError) as expired:
            await waiter

        assert expired.value.code == 'DB_POOL_ACQUIRE_TIMEOUT'
        cancelled = asyncio.create_task(acquire())

        await wait_for_waiters(pool, 1)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled

        assert not pool.admission.waiters
        await held.close()
        await acquire()
        assert pool.checkedout() == 0 and pool.admission.active == 0
        invalidated = await engine.connect()

        await invalidated.invalidate()
        await invalidated.close()
        await acquire()
        old = pool

        await engine.dispose()
        assert isinstance(engine.pool, BoundedAsyncPool)
        assert (
            engine.pool.admission.queue_limit == 1
            and engine.pool.acquire_timeout == 0.1
        )
        await acquire()
        assert old.admission.closed
        current = engine.pool

        assert isinstance(current, BoundedAsyncPool)
        held = await engine.connect()
        closing = asyncio.create_task(acquire())

        await wait_for_waiters(current, 1)
        await engine.dispose()
        with pytest.raises(DatabaseUnavailableError) as closed:
            await closing

        assert closed.value.code == "DB_POOL_CLOSED"
        await held.close()
        assert current.admission.active == 0
        await acquire()
    finally:
        await engine.dispose()


@pytest.mark.parametrize('deadline', ['connect', 'acquire'])
async def test_socket_stalled_handshake_times_out_and_closes(deadline: str) -> None:
    disconnected = asyncio.Event()

    async def stalled(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            await reader.read()
        finally:
            disconnected.set()
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(stalled, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    policy = DatabasePolicy(
        connection_limit=1,
        queue_limit=0,
        acquire_timeout_ms=500 if deadline == 'connect' else 50,
        connect_timeout_ms=50 if deadline == 'connect' else 500,
    )
    engine = build_database_engine(
        f'mysql+asyncmy://test:private-value-never-log@127.0.0.1:{port}/test',
        policy=policy,
    )

    try:
        with pytest.raises(DatabaseUnavailableError) as error:
            await engine.connect()

        assert error.value.code == (
            'DB_CONNECT_TIMEOUT' if deadline == 'connect' else 'DB_POOL_ACQUIRE_TIMEOUT'
        )
        await asyncio.wait_for(disconnected.wait(), 2)
        assert (
            isinstance(engine.pool, BoundedAsyncPool)
            and engine.pool.admission.active == 0
        )
        assert not engine.pool.admission.waiters and engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
        server.close()
        await server.wait_closed()


async def test_external_cancellation_during_handshake_closes_socket() -> None:
    disconnected = asyncio.Event()
    accepted = asyncio.Event()

    async def stalled(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        accepted.set()

        try:
            await reader.read()
        finally:
            disconnected.set()
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(stalled, '127.0.0.1', 0)
    engine = build_database_engine(
        f'mysql+asyncmy://test:test@127.0.0.1:{server.sockets[0].getsockname()[1]}/test',
        policy=DatabasePolicy(acquire_timeout_ms=5000),
    )

    async def connect() -> None:
        async with engine.connect():
            pass

    try:
        task = asyncio.create_task(connect())

        await asyncio.wait_for(accepted.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        await asyncio.wait_for(disconnected.wait(), 2)
        assert (
            isinstance(engine.pool, BoundedAsyncPool)
            and engine.pool.admission.active == 0
        )
    finally:
        await engine.dispose()
        server.close()
        await server.wait_closed()


async def test_database_rejection_uses_safe_503_envelope() -> None:
    from starlette.exceptions import HTTPException

    app = FastAPI()

    app.exception_handler(HTTPException)(http_exception_handler)

    @app.get('/')
    async def reject() -> None:
        raise DatabaseUnavailableError('DB_POOL_CAPACITY')

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        response = await client.get('/')

    assert (
        response.status_code == 503
        and response.json()['message'] == 'Database temporarily unavailable.'
    )
    assert set(response.json()) == {'status', 'message', 'timestamp'}
