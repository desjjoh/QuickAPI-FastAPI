import asyncio
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.v1.items.models.item_model import ItemResponse
from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.models.idempotency_model import idempotent
from app.config import database
from app.config.application import create_app
from app.config.environment import settings
from app.database.entities.idempotency_orm import IdempotencyORM
from app.database.entities.item_orm import ItemORM
from app.database.repositories.idempotency_repo import idempotency_repo
from app.database.repositories.item_repo import repo

from .helpers import ITEMS_URL, create_item

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]
KEY = {'Idempotency-Key': 'attempt-1'}


async def request_mutation(
    client: httpx.AsyncClient,
    operation: str,
    path: str,
    body: dict[str, object],
    *,
    keyed: bool = True,
) -> httpx.Response:
    return await client.request(
        'POST' if operation in ('create', 'delete') else operation.upper(),
        path + ('/delete' if operation == 'delete' else ''),
        json=body,
        headers=KEY if keyed else {},
    )


@pytest.mark.parametrize('operation', ['create', 'patch', 'put', 'delete'])
async def test_original_status_and_bytes_replay_after_later_changes_and_deletion(
    client: httpx.AsyncClient, database_engine: AsyncEngine, operation: str
) -> None:
    item = await create_item(client)
    path = ITEMS_URL if operation == 'create' else ITEMS_URL + item['id']
    body: dict[str, object] = {'name': 'Keyed', 'price': '12.34'}

    if operation != 'create':
        body['expected_version'] = 1

    if operation == 'delete':
        body = {'expected_version': 1}

    first = await request_mutation(client, operation, path, body)

    assert first.status_code == (201 if operation == 'create' else 200), first.text
    result = first.json()
    resource = ITEMS_URL + result['id']

    if operation != 'delete':
        later = await client.patch(
            resource, json={'name': 'Later', 'expected_version': result['version']}
        )

        assert later.status_code == 200
        removed = await client.post(
            resource + '/delete', json={'expected_version': later.json()['version']}
        )

        assert removed.status_code == 200

    replay = await request_mutation(client, operation, path, body)

    assert (replay.status_code, replay.content) == (first.status_code, first.content)
    assert (await client.get(resource)).status_code == 404
    async with database_engine.connect() as observer:
        assert (
            await observer.scalar(select(func.count()).select_from(IdempotencyORM)) == 1
        )


async def test_normalized_prices_aliases_and_object_order_replay(
    client: httpx.AsyncClient,
) -> None:
    first = await client.post(
        '/api/v1/items/', json={'name': 'Normalized', 'price': '01.20'}, headers=KEY
    )
    replay = await client.post(
        '/api/v1/items', json={'price': 1.2, 'name': 'Normalized'}, headers=KEY
    )

    assert first.status_code == replay.status_code == 201
    assert first.content == replay.content
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_app()), base_url='http://test'
    ) as restarted:
        replay_after_restart = await restarted.post(
            '/api/v1/items', json={'price': 1.2, 'name': 'Normalized'}, headers=KEY
        )

        assert (
            replay_after_restart.status_code == 201
            and replay_after_restart.content == first.content
        )

    changed = await client.post(
        '/api/v1/items', json={'name': 'Changed', 'price': 1.2}, headers=KEY
    )

    assert changed.status_code == 409
    assert (
        changed.json()['message']
        == 'Idempotency-Key was already used with a different payload.'
    )


async def test_operations_have_separate_scopes_but_other_item_ids_conflict(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        ITEMS_URL, json={'name': 'Scoped', 'price': 1}, headers=KEY
    )
    path = ITEMS_URL + created.json()['id']

    for operation, version in [('patch', 1), ('put', 2)]:
        response = await request_mutation(
            client,
            operation,
            path,
            {'name': 'Scoped', 'price': 1, 'expected_version': version},
        )

        assert response.status_code == 200 and response.json()['version'] == version + 1

    other = await create_item(client)
    conflict = await request_mutation(
        client,
        'patch',
        ITEMS_URL + other['id'],
        {'name': 'Scoped', 'price': 1, 'expected_version': 1},
    )

    assert conflict.status_code == 409
    assert (await client.get(ITEMS_URL + other['id'])).json() == other
    deleted = await request_mutation(client, 'delete', path, {'expected_version': 3})

    assert deleted.status_code == 200


@pytest.mark.parametrize('value', ['', ' ', 'a b', 'a,b', 'x' * 129, '\t', '\x7f'])
async def test_invalid_keys_never_claim_or_mutate(
    client: httpx.AsyncClient, database_engine: AsyncEngine, value: str
) -> None:
    response = await client.post(
        ITEMS_URL,
        json={'name': 'Invalid', 'price': 1},
        headers={'Idempotency-Key': value},
    )

    assert response.status_code == 400
    async with database_engine.connect() as observer:
        assert await observer.scalar(select(func.count()).select_from(ItemORM)) == 0
        assert (
            await observer.scalar(select(func.count()).select_from(IdempotencyORM)) == 0
        )


async def test_duplicate_header_is_rejected_and_header_is_allowed_by_cors(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        ITEMS_URL,
        json={'name': 'Duplicate', 'price': 1},
        headers=[('Idempotency-Key', 'one'), ('idempotency-key', 'one')],
    )

    assert response.status_code == 400
    preflight = await client.options(
        ITEMS_URL,
        headers={
            'Origin': 'http://localhost:3000',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Idempotency-Key,Content-Type',
        },
    )

    assert preflight.status_code == 204
    assert (
        'idempotency-key' in preflight.headers['access-control-allow-headers'].lower()
    )


async def test_validation_stale_and_size_failures_are_not_retained(
    client: httpx.AsyncClient,
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        await client.post(ITEMS_URL, json={'price': 1}, headers=KEY)
    ).status_code == 422
    monkeypatch.setattr(settings, 'IDEMPOTENCY_MAX_RESPONSE_BYTES', 1)
    failed = await client.post(
        ITEMS_URL, json={'name': 'Size', 'price': 1}, headers=KEY
    )

    assert failed.status_code == 500
    async with database_engine.connect() as observer:
        assert await observer.scalar(select(func.count()).select_from(ItemORM)) == 0
        assert (
            await observer.scalar(select(func.count()).select_from(IdempotencyORM)) == 0
        )

    monkeypatch.setattr(settings, 'IDEMPOTENCY_MAX_RESPONSE_BYTES', 65536)
    accepted = await client.post(
        ITEMS_URL, json={'name': 'Size', 'price': 1}, headers=KEY
    )

    assert accepted.status_code == 201
    path = ITEMS_URL + accepted.json()['id']
    stale = await request_mutation(
        client, 'patch', path, {'name': 'Stale', 'expected_version': 99}
    )

    assert stale.status_code == 409
    success = await request_mutation(
        client, 'patch', path, {'name': 'Valid', 'expected_version': 1}
    )

    assert success.status_code == 200 and success.json()['version'] == 2
    monkeypatch.setattr(settings, 'IDEMPOTENCY_MAX_RESPONSE_BYTES', 1)
    replay = await client.post(
        ITEMS_URL, json={'name': 'Size', 'price': 1}, headers=KEY
    )

    assert replay.content == accepted.content and replay.status_code == 201


async def test_replay_does_not_extend_expiry_and_expired_key_executes_again(
    client: httpx.AsyncClient, database_engine: AsyncEngine
) -> None:
    body = {'name': 'Expiry', 'price': 1}
    first = await client.post(ITEMS_URL, json=body, headers=KEY)

    async with database_engine.connect() as observer:
        before = (
            await observer.execute(
                select(IdempotencyORM.completed_at, IdempotencyORM.expires_at)
            )
        ).one()

        assert (before[1] - before[0]).total_seconds() == 86400

    assert (
        await client.post(ITEMS_URL, json=body, headers=KEY)
    ).content == first.content
    async with database_engine.begin() as observer:
        assert (
            await observer.execute(
                select(IdempotencyORM.completed_at, IdempotencyORM.expires_at)
            )
        ).one() == before
        await observer.execute(
            text(
                'UPDATE request_idempotency SET expires_at=TIMESTAMPADD(SECOND,-1,UTC_TIMESTAMP(3))'
            )
        )

    again = await client.post(ITEMS_URL, json=body, headers=KEY)

    assert again.status_code == 201 and again.json()['id'] != first.json()['id']


async def test_in_progress_key_conflicts_without_waiting_then_replays(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reached, release = asyncio.Event(), asyncio.Event()
    original = repo.create

    async def hold(session: AsyncSession, *, item_in: Any) -> ItemORM:
        item = await original(session, item_in=item_in)

        reached.set()
        await release.wait()

        return item

    monkeypatch.setattr(repo, 'create', hold)
    body = {'name': 'Concurrent', 'price': 1}
    first = asyncio.create_task(client.post(ITEMS_URL, json=body, headers=KEY))

    try:
        async with asyncio.timeout(3):
            await reached.wait()
            conflict = await client.post(ITEMS_URL, json=body, headers=KEY)

        assert conflict.status_code == 409
        assert (
            conflict.json()['message']
            == 'This idempotent request is already processing.'
        )
        release.set()
        accepted = await first
        replay = await client.post(ITEMS_URL, json=body, headers=KEY)

        assert (
            accepted.status_code == replay.status_code == 201
            and accepted.content == replay.content
        )
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)


async def test_precommit_failure_rolls_back_claim_and_item(
    client: httpx.AsyncClient,
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)
    fail = True

    def owned(**kwargs: Any) -> AsyncSession:
        session = factory(**kwargs)

        if fail:

            def reject(*_: object) -> None:
                raise RuntimeError('Injected precommit failure')

            event.listen(session.sync_session, 'before_commit', reject)

        return session

    monkeypatch.setattr(database, 'SessionLocal', owned)
    body = {'name': 'Commit', 'price': 1}

    assert (await client.post(ITEMS_URL, json=body, headers=KEY)).status_code == 500
    async with database_engine.connect() as observer:
        assert await observer.scalar(select(func.count()).select_from(ItemORM)) == 0
        assert (
            await observer.scalar(select(func.count()).select_from(IdempotencyORM)) == 0
        )

    fail = False

    assert (await client.post(ITEMS_URL, json=body, headers=KEY)).status_code == 201


async def test_cleanup_preserves_active_rows_and_is_bounded(
    client: httpx.AsyncClient,
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.common.services.idempotency_cleanup_service import (
        IdempotencyCleanupService,
    )

    for index in range(4):
        assert (
            await client.post(
                ITEMS_URL,
                json={'name': 'Clean', 'price': 1},
                headers={'Idempotency-Key': str(index)},
            )
        ).status_code == 201

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE request_idempotency SET expires_at=TIMESTAMPADD(SECOND,-1,UTC_TIMESTAMP(3)) WHERE scope_hash IN (SELECT scope_hash FROM (SELECT scope_hash FROM request_idempotency ORDER BY scope_hash LIMIT 3) AS expired)"
            )
        )

    monkeypatch.setattr(settings, 'IDEMPOTENCY_CLEANUP_BATCH_SIZE', 1)
    monkeypatch.setattr(settings, 'IDEMPOTENCY_CLEANUP_MAX_BATCHES', 2)
    cleanup = IdempotencyCleanupService()
    other_cleanup = IdempotencyCleanupService()

    await cleanup.start()
    await other_cleanup.start()

    try:
        assert await cleanup.sweep() == 2
        assert sum(await asyncio.gather(cleanup.sweep(), other_cleanup.sweep())) == 1
        async with database_engine.connect() as observer:
            assert (
                await observer.scalar(select(func.count()).select_from(IdempotencyORM))
                == 1
            )

        assert await cleanup.sweep() == 0
    finally:
        await cleanup.stop()
        await other_cleanup.stop()

    assert await cleanup.sweep() == 0


async def test_completed_claim_cannot_be_overwritten(
    client: httpx.AsyncClient, database_engine: AsyncEngine
) -> None:
    original = await client.post(
        ITEMS_URL, json={'name': 'Immutable', 'price': 1}, headers=KEY
    )
    factory = async_sessionmaker(database_engine)

    async with factory() as session:
        with pytest.raises(RuntimeError, match=r'processing.*claim'):
            async with session.begin():
                scope = await session.scalar(select(IdempotencyORM.scope_hash))

                assert scope is not None
                await idempotency_repo.complete(
                    session, scope, 201, b'{"changed":true}'
                )

    replay = await client.post(
        ITEMS_URL, json={'name': 'Immutable', 'price': 1}, headers=KEY
    )

    assert replay.status_code == 201 and replay.content == original.content


@pytest.mark.parametrize('operation', ['create', 'patch', 'put', 'delete'])
@pytest.mark.parametrize('failure', ['validation', 'render', 'completion'])
async def test_failed_preparation_rolls_back_claim_and_domain_write(
    client: httpx.AsyncClient,
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure: str,
) -> None:
    item = await create_item(client, 'Before', 1)
    path = ITEMS_URL if operation == 'create' else ITEMS_URL + item['id']
    body: dict[str, object] = {'name': 'After', 'price': 2}

    if operation != 'create':
        body['expected_version'] = 1

    if operation == 'delete':
        body = {'expected_version': 1}

    with monkeypatch.context() as patch:
        if failure == 'validation':

            def invalid(cls: type[ItemResponse], value: object) -> ItemResponse:
                raise ValueError('Injected response validation failure')

            patch.setattr(ItemResponse, 'model_validate', classmethod(invalid))
        elif failure == 'render':
            original = JSONResponse.render

            def render(self: JSONResponse, value: Any) -> bytes:
                if isinstance(value, dict) and 'id' in value:
                    raise ValueError('Injected render failure')

                return original(self, value)

            patch.setattr(JSONResponse, 'render', render)
        else:

            async def fail_completion(*args: Any, **kwargs: Any) -> None:
                raise RuntimeError('Injected completion failure')

            patch.setattr(idempotency_repo, 'complete', fail_completion)

        rejected = await request_mutation(client, operation, path, body)

        assert rejected.status_code == 500

    assert (await client.get(ITEMS_URL + item['id'])).json() == item
    async with database_engine.connect() as observer:
        assert (
            await observer.scalar(select(func.count()).select_from(IdempotencyORM)) == 0
        )
        assert await observer.scalar(select(func.count()).select_from(ItemORM)) == 1

    accepted = await request_mutation(client, operation, path, body)

    assert accepted.status_code == (201 if operation == 'create' else 200)
    async with database_engine.connect() as observer:
        assert (
            await observer.scalar(select(func.count()).select_from(IdempotencyORM)) == 1
        )


async def test_another_domain_uses_validated_inputs_and_dynamic_caller_scope(
    app: FastAPI,
) -> None:
    class Body(BaseModel):
        value: int

    router = APIRouter(route_class=ApplicationRoute)
    calls: list[int] = []

    @router.post('/widgets/{id}', status_code=201)
    @transactional
    @idempotent(
        operation='widgets.create',
        route='POST /widgets/:id',
        caller_scope=lambda request: request.headers.get('x-api-key', 'public'),
    )
    def widget(
        id: int,
        payload: Body,
        multiplier: int = Query(1),
        session: AsyncSession = Depends(database.get_session),
    ) -> dict[str, int]:
        assert session.in_transaction()
        calls.append(payload.value)

        return {'value': payload.value * multiplier + id}

    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        first = await client.post(
            '/widgets/01?multiplier=2',
            json={'value': 3},
            headers={**KEY, 'x-api-key': 'caller-a'},
        )

        assert first.status_code == 201 and first.json() == {'value': 7}
        replay = await client.post(
            '/widgets/1?multiplier=2',
            json={'value': 3, 'ignored': True},
            headers={**KEY, 'x-api-key': 'caller-a'},
        )

        assert replay.content == first.content
        changed = await client.post(
            '/widgets/1?multiplier=3',
            json={'value': 3},
            headers={**KEY, 'x-api-key': 'caller-a'},
        )

        assert changed.status_code == 409
        other = await client.post(
            '/widgets/1?multiplier=3',
            json={'value': 3},
            headers={**KEY, 'x-api-key': 'caller-b'},
        )

        assert other.status_code == 201 and other.json() == {'value': 10}

    assert calls == [3, 3]
