import asyncio

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.common.handlers.request_activity import RequestActivity
from app.common.models.idempotency_model import digest
from app.config import database
from app.config.database_transport import build_database_engine
from app.config.environment import settings
from app.database.entities.idempotency_orm import IdempotencyORM
from app.database.entities.item_orm import ItemORM

from .test_mutation_expiry import QueryGate, application, serving, settled

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('ending', ['timeout', 'disconnect'])
@pytest.mark.parametrize(
    'command,committed', [(b'COMMIT', True), (b'INSERT INTO ITEMS', False)]
)
async def test_lost_http_response_reconciles_committed_and_rolled_back_attempts(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    ending: str,
    command: bytes,
    committed: bool,
) -> None:
    gate = QueryGate(database_engine, command, 'after')
    relay = await asyncio.start_server(gate.accept, '127.0.0.1', 0)
    engine = build_database_engine(
        database_engine.url.set(
            host='127.0.0.1', port=relay.sockets[0].getsockname()[1]
        )
    )

    monkeypatch.setattr(
        database,
        'SessionLocal',
        async_sessionmaker(engine, expire_on_commit=False, autoflush=False),
    )
    abandoned = asyncio.Event()
    original = RequestActivity.abandon

    def abandon(activity: RequestActivity, reason: str) -> None:
        original(activity, reason)
        abandoned.set()

    monkeypatch.setattr(RequestActivity, 'abandon', abandon)
    app = application(0.2 if ending == 'timeout' else 3)
    pending: asyncio.Task[httpx.Response] | None = None
    writer: asyncio.StreamWriter | None = None

    try:
        async with (
            serving(app) as base,
            httpx.AsyncClient(base_url=base, timeout=5) as client,
        ):
            body = b'{"name":"Lost HTTP","price":1}'
            headers = {
                'Idempotency-Key': 'lost-http',
                'Content-Type': 'application/json',
            }

            if ending == 'timeout':
                pending = asyncio.create_task(
                    client.post('/api/v1/items', content=body, headers=headers)
                )
            else:
                _, writer = await asyncio.open_connection(
                    '127.0.0.1', int(base.rsplit(':', 1)[1])
                )

                writer.write(
                    f'POST /api/v1/items HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nIdempotency-Key: lost-http\r\nContent-Length: {len(body)}\r\n\r\n'.encode()
                    + body
                )
                await writer.drain()

            await asyncio.wait_for(gate.reached.wait(), 4)
            async with database_engine.connect() as observer:
                original_body = await observer.scalar(
                    select(IdempotencyORM.response_body)
                )

                assert (original_body is not None) == committed

            if pending is not None:
                assert (await pending).status_code == 408
            else:
                assert writer is not None
                writer.close()
                await writer.wait_closed()
                await asyncio.wait_for(abandoned.wait(), 3)

            in_progress = await client.post(
                '/api/v1/items', content=body, headers=headers
            )

            assert in_progress.status_code == 409
            gate.release.set()
            await settled(app)
            async with database_engine.connect() as observer:
                assert await observer.scalar(
                    select(func.count()).select_from(ItemORM)
                ) == int(committed)
                assert await observer.scalar(
                    select(func.count()).select_from(IdempotencyORM)
                ) == int(committed)

            retry = await client.post('/api/v1/items/', content=body, headers=headers)

            assert retry.status_code == 201
            if committed:
                assert retry.content == original_body

            replay = await client.post('/api/v1/items', content=body, headers=headers)

            assert replay.status_code == 201 and replay.content == retry.content
            async with database_engine.connect() as observer:
                assert (
                    await observer.scalar(select(func.count()).select_from(ItemORM))
                    == 1
                )
    finally:
        gate.release.set()
        if writer is not None:
            writer.close()

        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)

        await engine.dispose()
        relay.close()
        await relay.wait_closed()
        async with asyncio.timeout(3):
            while gate.tasks:
                await asyncio.sleep(0.001)


@pytest.mark.parametrize(
    'command,phase,committed',
    [
        (b'SELECT GET_LOCK', 'after', False),
        (b'COMMIT', 'before', False),
        (b'COMMIT', 'after', True),
        (b'SELECT RELEASE_LOCK', 'after', True),
    ],
)
async def test_uncertain_sql_acknowledgements_release_locks_and_reconcile_retries(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    command: bytes,
    phase: str,
    committed: bool,
) -> None:
    gate = QueryGate(database_engine, command, phase)
    relay = await asyncio.start_server(gate.accept, '127.0.0.1', 0)
    engine = build_database_engine(
        database_engine.url.set(
            host='127.0.0.1', port=relay.sockets[0].getsockname()[1]
        )
    )

    monkeypatch.setattr(
        database,
        'SessionLocal',
        async_sessionmaker(engine, expire_on_commit=False, autoflush=False),
    )
    app = application(2)
    key = 'network-attempt'
    namespace = digest([settings.APP_NAME, database_engine.url.database])
    scope = digest(
        [
            'idempotency-v1',
            namespace,
            'public',
            'items.create',
            'POST /api/v1/items',
            key,
        ]
    )
    pending: asyncio.Task[httpx.Response] | None = None

    try:
        async with (
            serving(app) as base,
            httpx.AsyncClient(base_url=base, timeout=5) as client,
        ):
            body = {'name': 'Transport', 'price': 1}
            pending = asyncio.create_task(
                client.post(
                    '/api/v1/items', json=body, headers={'Idempotency-Key': key}
                )
            )

            async with asyncio.timeout(4):
                await gate.reached.wait()

            gate.drop = True

            gate.release.set()
            response = await pending

            assert response.status_code in (500, 408)
            await settled(app)
            async with database_engine.connect() as observer:
                assert await observer.scalar(
                    select(func.count()).select_from(ItemORM)
                ) == int(committed)
                assert await observer.scalar(
                    select(func.count()).select_from(IdempotencyORM)
                ) == int(committed)
                async with asyncio.timeout(3):
                    while (
                        await observer.scalar(
                            text('SELECT IS_FREE_LOCK(:name)'), {'name': scope}
                        )
                        != 1
                    ):
                        await asyncio.sleep(0.01)

            retry = await client.post(
                '/api/v1/items/', json=body, headers={'Idempotency-Key': key}
            )

            assert retry.status_code == 201, retry.text
            replay = await client.post(
                '/api/v1/items', json=body, headers={'Idempotency-Key': key}
            )

            assert replay.status_code == 201 and replay.content == retry.content
            async with database_engine.connect() as observer:
                assert (
                    await observer.scalar(select(func.count()).select_from(ItemORM))
                    == 1
                )
                assert (
                    await observer.scalar(
                        select(func.count()).select_from(IdempotencyORM)
                    )
                    == 1
                )
                assert (
                    await observer.scalar(
                        text('SELECT IS_FREE_LOCK(:name)'), {'name': scope}
                    )
                    == 1
                )
    finally:
        gate.release.set()
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)

        await engine.dispose()
        relay.close()
        await relay.wait_closed()
        async with asyncio.timeout(3):
            while gate.tasks:
                await asyncio.sleep(0.001)
