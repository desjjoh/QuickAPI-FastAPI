"""Socket HTTP and real MySQL evidence for abandoned mutation ownership."""

import asyncio
import json
import socket
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Literal, cast

import httpx
import pytest
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, Request
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.handlers.database_pool import BoundedAsyncPool
from app.common.handlers.request_activity import RequestActivity, request_activity
from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware
from app.config import database
from app.config.application import create_app
from app.config.database_transport import DatabasePolicy, build_database_engine
from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import repo

pytestmark = pytest.mark.integration


@asynccontextmanager
async def serving(app: FastAPI) -> AsyncGenerator[str, None]:
    listener = socket.socket()

    listener.bind(('127.0.0.1', 0))
    listener.setblocking(False)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            lifespan='off',
            log_config=None,
            access_log=False,
            ws='none',
            timeout_graceful_shutdown=2,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))

    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task

                    raise AssertionError('Server did not start')

                await asyncio.sleep(0.001)

        yield f'http://127.0.0.1:{listener.getsockname()[1]}'
    finally:
        server.should_exit = True

        try:
            await asyncio.wait_for(task, 5)
        finally:
            listener.close()


def application(seconds: float = 0.25) -> FastAPI:
    app = create_app()

    for middleware in app.user_middleware:
        if middleware.cls is RequestTimeoutASGIMiddleware:
            middleware.kwargs['total_timeout'] = seconds

    return app


async def settled(app: FastAPI) -> None:
    # Include dependency teardown, session close and ASGI task completion.
    async with asyncio.timeout(5):
        while app.state.request_work.tasks:
            await asyncio.sleep(0.001)


@pytest.mark.parametrize('method', ['POST', 'PATCH', 'PUT', 'DELETE'])
@pytest.mark.parametrize('ending', ['timeout', 'disconnect'])
async def test_abandoned_write_settles_then_rolls_back_without_late_response(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    ending: str,
) -> None:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    monkeypatch.setattr(database, 'SessionLocal', factory)
    async with factory() as seed, seed.begin():
        item = ItemORM(name='Before', price=Decimal('1'))

        seed.add(item)
        await seed.flush()
        identifier = item.id

    written, release = asyncio.Event(), asyncio.Event()
    disconnected = asyncio.Event()
    original_abandon = RequestActivity.abandon

    def abandon(activity: RequestActivity, reason: str) -> None:
        original_abandon(activity, reason)
        if reason == 'Request disconnected.':
            disconnected.set()

    monkeypatch.setattr(RequestActivity, 'abandon', abandon)
    cancelled = False
    operation = (
        'create' if method == 'POST' else 'delete' if method == 'DELETE' else 'update'
    )
    original = getattr(repo, operation)

    async def hold(*args: Any, **kwargs: Any) -> Any:
        nonlocal cancelled
        value = await original(*args, **kwargs)

        written.set()

        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled = True

            await release.wait()

        return value

    monkeypatch.setattr(repo, operation, hold)
    app = application(0.25 if ending == 'timeout' else 5)

    async with serving(app) as base, httpx.AsyncClient(base_url=base) as client:
        path = '/api/v1/items/' if method == 'POST' else f'/api/v1/items/{identifier}'
        payload = (
            {'expected_version': 1}
            if method == 'DELETE'
            else {'name': 'After', 'price': 2, 'expected_version': 1}
        )

        if method == 'DELETE':
            path += '/delete'

        wire_method = 'POST' if method == 'DELETE' else method
        request: asyncio.Task[httpx.Response] | None = None
        writer: asyncio.StreamWriter | None = None

        try:
            if ending == 'timeout':
                request = asyncio.create_task(
                    client.request(wire_method, path, json=payload)
                )
            else:
                body = json.dumps(payload).encode() if payload else b''
                _, writer = await asyncio.open_connection(
                    '127.0.0.1', int(base.rsplit(':', 1)[1])
                )
                content_type = 'Content-Type: application/json\r\n' if payload else ''

                writer.write(
                    f'{wire_method} {path} HTTP/1.1\r\nHost: localhost\r\n{content_type}Content-Length: {len(body)}\r\n\r\n'.encode()
                    + body
                )
                await writer.drain()

            await asyncio.wait_for(written.wait(), 3)
            if request is not None:
                response = await asyncio.wait_for(request, 3)

                assert response.status_code == 408
                assert response.json()['message'] == 'Total request timeout exceeded.'
            else:
                assert writer is not None
                writer.close()
                await writer.wait_closed()
                await asyncio.wait_for(disconnected.wait(), 3)

            assert not cancelled
            assert app.state.request_work.tasks
            release.set()
            await settled(app)
            async with factory() as observer:
                rows = list(await observer.scalars(select(ItemORM.name)))

                assert rows == ['Before']

            # A following mutation on the same server succeeds; the late result
            # neither corrupts its connection nor poisons session/pool state.
            following = await client.post(
                '/api/v1/items/', json={'name': 'Recovered', 'price': 1}
            )

            assert following.status_code == 201
        finally:
            release.set()
            if request is not None:
                await asyncio.gather(request, return_exceptions=True)

            if writer is not None:
                writer.close()

            await settled(app)


async def test_expiry_during_pool_wait_prevents_business_sql_after_checkout(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = build_database_engine(
        database_engine.url,
        policy=DatabasePolicy(connection_limit=1, acquire_timeout_ms=3000),
    )
    pool = cast(BoundedAsyncPool, engine.pool)

    monkeypatch.setattr(
        database, 'SessionLocal', async_sessionmaker(engine, expire_on_commit=False)
    )
    held = await engine.connect()
    business_sql: list[str] = []

    def executed(_: object, __: object, statement: str, *args: object) -> None:
        business_sql.append(statement)

    event.listen(engine.sync_engine, 'before_cursor_execute', executed)
    app = application()

    try:
        async with serving(app) as base, httpx.AsyncClient(base_url=base) as client:
            pending = asyncio.create_task(
                client.post('/api/v1/items/', json={'name': 'Too late', 'price': 1})
            )

            async with asyncio.timeout(3):
                while not pool.admission.waiters:
                    await asyncio.sleep(0.001)

            assert (await pending).status_code == 408
            await held.close()
            await settled(app)
            assert pool.admission.active == 0 and not pool.admission.waiters
            assert not business_sql
            async with database_engine.connect() as observer:
                assert not list(await observer.scalars(select(ItemORM.name)))

            assert (
                await client.post(
                    '/api/v1/items/', json={'name': 'Recovered', 'price': 1}
                )
            ).status_code == 201
    finally:
        await held.close()
        await engine.dispose()


@pytest.mark.parametrize('catch_cancellation', [False, True])
async def test_clock_guard_rolls_back_even_without_timeout_callback(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    catch_cancellation: bool,
) -> None:
    monkeypatch.setattr(
        database,
        'SessionLocal',
        async_sessionmaker(database_engine, expire_on_commit=False),
    )
    router = APIRouter(route_class=ApplicationRoute)

    @router.post('/clock')
    @transactional
    async def clock(
        request: Request, db: AsyncSession = Depends(database.get_session)
    ) -> dict[str, bool]:
        await repo.create(db, item_in={'name': 'Expired', 'price': Decimal('1')})
        if catch_cancellation:
            task = asyncio.current_task()

            assert task is not None
            task.cancel()

            try:
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                pass

        request_activity(request.scope).expires_at = time.monotonic() - 1

        return {'ok': True}

    app = application(5)

    app.include_router(router)
    async with serving(app) as base, httpx.AsyncClient(base_url=base) as client:
        response = await client.post('/clock', json={})

        assert response.status_code == 408
        await settled(app)

    async with database_engine.connect() as observer:
        assert not list(await observer.scalars(select(ItemORM.name)))


class QueryGate:
    """Plaintext disposable-MySQL relay with one command/result barrier.

    Packet framing, rather than arbitrary TCP chunks, makes the barrier exact.
    This deliberately does not implement TLS or a general MySQL proxy.
    """

    def __init__(self, engine: AsyncEngine, query: bytes, phase: str) -> None:
        self.host = engine.url.host or '127.0.0.1'
        self.port = engine.url.port or 3306
        self.query, self.phase = query, phase
        self.reached, self.release = asyncio.Event(), asyncio.Event()
        self.drop = False
        self.used = False
        self.armed = True
        self.tasks: set[asyncio.Task[None]] = set()

    async def barrier(self) -> None:
        self.used = True

        self.reached.set()
        await self.release.wait()
        if self.drop:
            raise ConnectionAbortedError('Test-owned MySQL connection loss')

    async def accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()

        assert task is not None
        self.tasks.add(task)
        upstream: asyncio.StreamWriter | None = None
        pipes: list[asyncio.Task[None]] = []
        result_pending = False

        async def pipe(
            source: asyncio.StreamReader, target: asyncio.StreamWriter, downstream: bool
        ) -> None:
            nonlocal result_pending
            while True:
                header = await source.readexactly(4)
                body = await source.readexactly(int.from_bytes(header[:3], 'little'))

                if (
                    not downstream
                    and self.armed
                    and not self.used
                    and body.startswith(b'\x03')
                    and body[1:].upper().startswith(self.query)
                ):
                    if self.phase == 'before':
                        await self.barrier()
                    else:
                        result_pending = True
                elif downstream and result_pending:
                    result_pending = False

                    await self.barrier()

                target.write(header + body)
                await target.drain()

        try:
            remote, upstream = await asyncio.open_connection(self.host, self.port)
            pipes = [
                asyncio.create_task(pipe(reader, upstream, False)),
                asyncio.create_task(pipe(remote, writer, True)),
            ]
            done, _ = await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)

            for completed in done:
                await completed
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            for pending in pipes:
                pending.cancel()

            await asyncio.gather(*pipes, return_exceptions=True)
            for stream in (writer, upstream):
                if stream is not None:
                    stream.close()

                    try:
                        await stream.wait_closed()
                    except OSError:
                        pass

            self.tasks.discard(task)


@pytest.mark.parametrize('phase', ['before', 'after'])
async def test_connection_loss_during_rollback_retires_lease_and_recovers(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    gate = QueryGate(database_engine, b'ROLLBACK', phase)
    # SQLAlchemy's first-connection setup performs its own rollback. Arm only
    # after setup so the fault targets rollback of an actual application write.
    gate.armed = False
    relay = await asyncio.start_server(gate.accept, '127.0.0.1', 0)
    engine = build_database_engine(
        database_engine.url.set(
            host='127.0.0.1', port=relay.sockets[0].getsockname()[1]
        ),
        policy=DatabasePolicy(connection_limit=1, acquire_timeout_ms=3000),
    )
    pool = cast(BoundedAsyncPool, engine.pool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sessions: list[AsyncSession] = []
    invalidated: list[bool] = []

    def owned(**kwargs: Any) -> AsyncSession:
        session = factory(**kwargs)

        sessions.append(session)

        return session

    def invalidate(*_: object) -> None:
        invalidated.append(True)

    event.listen(engine.sync_engine, 'invalidate', invalidate)
    monkeypatch.setattr(database, 'SessionLocal', owned)
    connection_id: int | None = None
    router = APIRouter(route_class=ApplicationRoute)

    @router.post('/rollback-fault')
    @transactional
    async def operation(
        db: AsyncSession = Depends(database.get_session),
    ) -> dict[str, bool]:
        nonlocal connection_id
        connection_id = int(
            (await db.execute(text('SELECT CONNECTION_ID()'))).scalar_one()
        )

        await repo.create(db, item_in={'name': 'Discarded', 'price': Decimal('1')})

        raise RuntimeError('Injected preparation failure after a real write')

    app = application(5)

    app.include_router(router)

    try:
        async with engine.connect() as warm:
            await warm.execute(text('SELECT 1'))

        gate.armed = True

        async with serving(app) as base, httpx.AsyncClient(base_url=base) as client:
            failed = asyncio.create_task(client.post('/rollback-fault', json={}))
            recovery: asyncio.Task[httpx.Response] | None = None

            try:
                await asyncio.wait_for(gate.reached.wait(), 3)
                assert connection_id is not None
                assert pool.admission.active == 1 and not failed.done()
                async with database_engine.connect() as observer:
                    assert not list(await observer.scalars(select(ItemORM.name)))

                recovery = asyncio.create_task(
                    client.post(
                        '/api/v1/items/', json={'name': 'Recovered', 'price': 1}
                    )
                )

                async with asyncio.timeout(3):
                    while not pool.admission.waiters:
                        await asyncio.sleep(0.001)

                # No reuse or capacity release while rollback still owns the lease.
                assert pool.admission.active == 1 and not recovery.done()
                gate.drop = True

                gate.release.set()
                response = await asyncio.wait_for(failed, 3)

                assert response.status_code == 500
                assert response.json()['message'] == 'Internal Server Error'
                assert (await asyncio.wait_for(recovery, 3)).status_code == 201
                await settled(app)
                assert invalidated and all(
                    not session.in_transaction() for session in sessions
                )
                assert pool.admission.active == 0 and not pool.admission.waiters
                async with asyncio.timeout(3):
                    while True:
                        async with database_engine.connect() as observer:
                            processes = (
                                (await observer.execute(text('SHOW PROCESSLIST')))
                                .mappings()
                                .all()
                            )

                        if not any(
                            int(row['Id']) == connection_id for row in processes
                        ):
                            break

                        await asyncio.sleep(0.01)

                async with database_engine.connect() as observer:
                    assert list(await observer.scalars(select(ItemORM.name))) == [
                        'Recovered'
                    ]
            finally:
                gate.release.set()
                await asyncio.gather(
                    failed,
                    *([recovery] if recovery is not None else []),
                    return_exceptions=True,
                )
                await settled(app)
    finally:
        gate.release.set()
        await engine.dispose()
        relay.close()
        await relay.wait_closed()
        async with asyncio.timeout(3):
            while gate.tasks:
                await asyncio.sleep(0.001)


@pytest.mark.parametrize('cleanup_error', [False, True])
async def test_lost_http_response_after_confirmed_commit_does_not_undo_data(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_error: bool,
) -> None:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    closed, release = asyncio.Event(), asyncio.Event()
    first = True

    def owned(**kwargs: Any) -> AsyncSession:
        nonlocal first
        session = factory(**kwargs)

        if first:
            first = False
            original_close = session.close

            async def close() -> None:
                await original_close()
                closed.set()
                await release.wait()
                if cleanup_error:
                    raise RuntimeError('Injected post-commit cleanup failure')

            monkeypatch.setattr(session, 'close', close)

        return session

    monkeypatch.setattr(database, 'SessionLocal', owned)
    app = application()

    async with serving(app) as base, httpx.AsyncClient(base_url=base) as client:
        request = asyncio.create_task(
            client.post('/api/v1/items/', json={'name': 'Confirmed', 'price': 1})
        )

        try:
            await asyncio.wait_for(closed.wait(), 3)
            async with database_engine.connect() as observer:
                assert list(await observer.scalars(select(ItemORM.name))) == [
                    'Confirmed'
                ]

            assert (await request).status_code == 408
            release.set()
            await settled(app)
            assert (
                await client.post(
                    '/api/v1/items/', json={'name': 'Recovered', 'price': 1}
                )
            ).status_code == 201
            async with database_engine.connect() as observer:
                assert sorted(await observer.scalars(select(ItemORM.name))) == [
                    'Confirmed',
                    'Recovered',
                ]
        finally:
            release.set()
            await asyncio.gather(request, return_exceptions=True)
            await settled(app)


@pytest.mark.parametrize(
    'query,phase,drop,committed',
    [
        (b'INSERT', 'after', False, False),
        (b'INSERT', 'after', True, False),
        (b'COMMIT', 'before', False, True),
        (b'COMMIT', 'before', True, False),
        (b'COMMIT', 'after', False, True),
        (b'COMMIT', 'after', True, True),
    ],
)
async def test_real_mysql_results_and_commit_acknowledgement_loss(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    query: bytes,
    phase: Literal['before', 'after'],
    drop: bool,
    committed: bool,
) -> None:
    gate = QueryGate(database_engine, query, phase)
    relay = await asyncio.start_server(gate.accept, '127.0.0.1', 0)
    engine = build_database_engine(
        database_engine.url.set(
            host='127.0.0.1', port=relay.sockets[0].getsockname()[1]
        )
    )
    pool = cast(BoundedAsyncPool, engine.pool)

    monkeypatch.setattr(
        database, 'SessionLocal', async_sessionmaker(engine, expire_on_commit=False)
    )
    invalidated: list[bool] = []

    def invalidate(*_: object) -> None:
        invalidated.append(True)

    event.listen(engine.sync_engine, 'invalidate', invalidate)
    sessions: list[AsyncSession] = []
    factory = async_sessionmaker(engine, expire_on_commit=False)

    def owned(**kwargs: Any) -> AsyncSession:
        session = factory(**kwargs)

        sessions.append(session)

        return session

    monkeypatch.setattr(database, 'SessionLocal', owned)
    app = application(0.4)

    try:
        async with serving(app) as base, httpx.AsyncClient(base_url=base) as client:
            request = asyncio.create_task(
                client.post('/api/v1/items/', json={'name': 'Unconfirmed', 'price': 1})
            )

            try:
                await asyncio.wait_for(gate.reached.wait(), 3)
                # Receipt of the COMMIT OK packet proves the server completed it,
                # even though this relay has not delivered that acknowledgement.
                async with database_engine.connect() as observer:
                    visible = list(await observer.scalars(select(ItemORM.name)))

                assert visible == (
                    ['Unconfirmed'] if query == b'COMMIT' and phase == 'after' else []
                )
                assert (await asyncio.wait_for(request, 3)).status_code == 408
                assert pool.admission.active == 1
                gate.drop = drop

                gate.release.set()
                await settled(app)
                assert pool.admission.active == 0 and not pool.admission.waiters
                assert all(not session.in_transaction() for session in sessions)
                assert bool(invalidated) == drop
                async with database_engine.connect() as observer:
                    visible = list(await observer.scalars(select(ItemORM.name)))

                assert visible == (['Unconfirmed'] if committed else [])
                # Lost acknowledgements must not cause replay; exactly one new
                # request, with a recovered/replacement lease, creates one row.
                following = await client.post(
                    '/api/v1/items/', json={'name': 'Recovered', 'price': 1}
                )

                assert following.status_code == 201
                async with database_engine.connect() as observer:
                    names = list(await observer.scalars(select(ItemORM.name)))

                assert sorted(names) == sorted(
                    (['Unconfirmed'] if committed else []) + ['Recovered']
                )
            finally:
                gate.release.set()
                await asyncio.gather(request, return_exceptions=True)
                await settled(app)
    finally:
        gate.release.set()
        await engine.dispose()
        relay.close()
        await relay.wait_closed()
        async with asyncio.timeout(3):
            while gate.tasks:
                await asyncio.sleep(0.001)


@pytest.mark.parametrize('ending', ['disconnect', 'cancel'])
async def test_interruption_after_server_commit_preserves_data_and_recovers(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    ending: str,
) -> None:
    gate = QueryGate(database_engine, b'COMMIT', 'after')
    relay = await asyncio.start_server(gate.accept, '127.0.0.1', 0)
    engine = build_database_engine(
        database_engine.url.set(
            host='127.0.0.1', port=relay.sockets[0].getsockname()[1]
        )
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owners: list[asyncio.Task[Any]] = []
    sessions: list[AsyncSession] = []

    def owned(**kwargs: Any) -> AsyncSession:
        task = asyncio.current_task()

        assert task is not None
        owners.append(task)
        session = factory(**kwargs)

        sessions.append(session)

        return session

    monkeypatch.setattr(database, 'SessionLocal', owned)
    disconnected = asyncio.Event()
    original_abandon = RequestActivity.abandon

    def abandon(activity: RequestActivity, reason: str) -> None:
        original_abandon(activity, reason)
        if reason == 'Request disconnected.':
            disconnected.set()

    monkeypatch.setattr(RequestActivity, 'abandon', abandon)
    app = application(5)

    try:
        async with serving(app) as base, httpx.AsyncClient(base_url=base) as client:
            reader, writer = await asyncio.open_connection(
                '127.0.0.1', int(base.rsplit(':', 1)[1])
            )
            body = b'{"name":"Committed","price":1}'

            writer.write(
                f'POST /api/v1/items/ HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()
                + body
            )
            await writer.drain()

            try:
                await asyncio.wait_for(gate.reached.wait(), 3)
                if ending == 'disconnect':
                    writer.close()
                    await writer.wait_closed()
                    await asyncio.wait_for(disconnected.wait(), 3)
                    assert not owners[0].done()
                    gate.release.set()
                else:
                    # Server/shutdown cancellation is still allowed to interrupt
                    # work. It cannot undo a COMMIT already completed in MySQL.
                    owners[0].cancel()
                    wire = await asyncio.wait_for(reader.read(), 3)

                    assert b'201 Created' not in wire
                    gate.release.set()

                await settled(app)
                assert all(not session.in_transaction() for session in sessions)
                async with database_engine.connect() as observer:
                    assert list(await observer.scalars(select(ItemORM.name))) == [
                        'Committed'
                    ]

                assert (
                    await client.post(
                        '/api/v1/items/', json={'name': 'Recovered', 'price': 1}
                    )
                ).status_code == 201
            finally:
                gate.release.set()
                writer.close()
                await writer.wait_closed()
                await settled(app)
    finally:
        gate.release.set()
        await engine.dispose()
        relay.close()
        await relay.wait_closed()
        async with asyncio.timeout(3):
            while gate.tasks:
                await asyncio.sleep(0.001)
