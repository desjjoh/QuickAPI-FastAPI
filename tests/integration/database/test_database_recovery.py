import asyncio
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.common.handlers.database_pool import BoundedAsyncPool
from app.common.handlers.database_readiness import DatabaseReadiness
from app.config import database
from app.config.application import create_app
from app.config.database_transport import DatabasePolicy, build_database_engine

pytestmark = pytest.mark.integration


class MysqlProxy:
    """Test-owned TCP relay: disconnect or stall real MySQL protocol traffic."""

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.forward = asyncio.Event()

        self.forward.set()
        self.writers: set[asyncio.StreamWriter] = set()
        self.tasks: set[asyncio.Task[None]] = set()
        self.accepting = True

    async def accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()

        assert task is not None
        self.tasks.add(task)
        self.writers.add(writer)
        upstream: asyncio.StreamWriter | None = None

        async def pipe(
            source: asyncio.StreamReader,
            target: asyncio.StreamWriter,
            downstream: bool = False,
        ) -> None:
            while data := await source.read(65536):
                if downstream:
                    await self.forward.wait()

                target.write(data)
                await target.drain()

        try:
            if not self.accepting:
                return

            remote, upstream = await asyncio.open_connection(self.host, self.port)

            self.writers.add(upstream)
            workers = [
                asyncio.create_task(pipe(reader, upstream)),
                asyncio.create_task(pipe(remote, writer, downstream=True)),
            ]

            try:
                await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for worker in workers:
                    worker.cancel()

                await asyncio.gather(*workers, return_exceptions=True)
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            self.tasks.discard(task)
            for stream in (writer, upstream):
                if stream is not None:
                    stream.close()
                    self.writers.discard(stream)

                    try:
                        await stream.wait_closed()
                    except (OSError, asyncio.CancelledError):
                        pass

                    self.writers.discard(stream)

            self.tasks.discard(task)

    async def disconnect(self) -> None:
        for writer in list(self.writers):
            writer.close()

        for task in list(self.tasks):
            task.cancel()

        await asyncio.gather(*list(self.tasks), return_exceptions=True)


@asynccontextmanager
async def running_api() -> AsyncGenerator[str, None]:
    listener = socket.socket()

    listener.bind(('127.0.0.1', 0))
    listener.setblocking(False)
    server = uvicorn.Server(
        uvicorn.Config(create_app(), log_config=None, access_log=False, ws="none")
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))

    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                    pytest.fail('API failed to start')

                await asyncio.sleep(0.01)

        yield f'http://127.0.0.1:{listener.getsockname()[1]}'
    finally:
        server.should_exit = True

        try:
            await asyncio.wait_for(task, 5)
        finally:
            listener.close()


async def test_real_readiness_and_stopped_state(database_engine: AsyncEngine) -> None:
    probe = DatabaseReadiness(database_engine, cache_ms=0)

    assert await probe.check() is False
    probe.resume()
    assert all(await asyncio.gather(*(probe.check() for _ in range(20))))
    await probe.stop()
    assert await probe.check() is False


async def test_mysql_outage_stall_stale_and_recovery_on_running_api(
    database_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = database_engine.url
    relay = MysqlProxy(url.host or '127.0.0.1', url.port or 3306)
    proxy = await asyncio.start_server(relay.accept, '127.0.0.1', 0)
    port = proxy.sockets[0].getsockname()[1]
    engine = build_database_engine(
        url.set(host='127.0.0.1', port=port),
        policy=DatabasePolicy(
            connection_limit=1, queue_limit=2, acquire_timeout_ms=500
        ),
    )
    pool = engine.pool

    assert isinstance(pool, BoundedAsyncPool)
    probe = DatabaseReadiness(engine, timeout_ms=100, cache_ms=20)

    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'database_readiness', probe)
    monkeypatch.setattr(database, 'SessionLocal', async_sessionmaker(engine))

    async def connection_id() -> int:
        async with engine.connect() as connection:
            return int(
                (await connection.execute(text('SELECT CONNECTION_ID()'))).scalar_one()
            )

    async def gone(identifier: int) -> None:
        async with asyncio.timeout(3):
            while True:
                async with database_engine.connect() as control:
                    ids = (
                        (await control.execute(text('SHOW PROCESSLIST')))
                        .mappings()
                        .all()
                    )

                if not any(int(row['Id']) == identifier for row in ids):
                    return

                await asyncio.sleep(0.02)

    try:
        async with running_api() as base, httpx.AsyncClient(base_url=base) as client:

            async def recovered() -> None:
                async with asyncio.timeout(3):
                    while (await client.get('/ready')).status_code != 200:
                        await asyncio.sleep(0.03)

                response = await client.get('/api/v1/items/')

                assert response.status_code == 200
                async with asyncio.timeout(2):
                    while pool.admission.active:
                        await asyncio.sleep(0.001)

                assert not pool.admission.waiters

            await recovered()
            for _ in range(3):
                identifier = await connection_id()
                relay.accepting = False

                await relay.disconnect()
                await asyncio.sleep(0.03)
                unavailable = await client.get('/ready')

                assert unavailable.status_code == 503
                assert set(unavailable.json()) == {'ready', 'status', 'timestamp'}
                assert (await client.get('/health')).json()['alive'] is True
                await gone(identifier)
                relay.accepting = True

                await recovered()

            # A real stale idle lease is invalidated, then a replacement succeeds.
            identifier = await connection_id()

            async with database_engine.connect() as control:
                await control.execute(text(f'KILL CONNECTION {identifier}'))

            await gone(identifier)
            await asyncio.sleep(0.03)
            assert (await client.get('/ready')).status_code == 503
            await recovered()

            identifier = await connection_id()

            relay.forward.clear()
            await asyncio.sleep(0.03)
            requests = [asyncio.create_task(client.get('/ready')) for _ in range(20)]

            assert (await client.get('/health')).status_code == 200
            results = await asyncio.wait_for(asyncio.gather(*requests), 2)

            assert all(result.status_code == 503 for result in results)
            await gone(identifier)
            assert pool.admission.active == 0 and not pool.admission.waiters
            relay.forward.set()
            await recovered()

            # Repeated expired probes cannot accumulate acquisition waiters.
            held = await engine.connect()

            try:
                for _ in range(3):
                    await asyncio.sleep(0.03)
                    assert (await client.get('/ready')).status_code == 503
                    assert not pool.admission.waiters and pool.admission.active == 1
            finally:
                await held.close()

            await recovered()

        assert await probe.check() is False
        assert pool.admission.active == 0
    finally:
        relay.forward.set()
        await probe.stop()
        await engine.dispose()
        proxy.close()
        await proxy.wait_closed()
        await relay.disconnect()
        assert not relay.tasks and not relay.writers
