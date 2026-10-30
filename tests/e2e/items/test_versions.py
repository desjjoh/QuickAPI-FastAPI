import asyncio

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import repo

from .helpers import ITEMS_URL, MISSING_ID, create_item

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]
CONFLICT = 'Item version conflict; reload the item before retrying.'


async def mutate(
    client: httpx.AsyncClient, path: str, operation: str, version: object = 1
) -> httpx.Response:
    body: dict[str, object] = {'expected_version': version}

    if operation != 'delete':
        body.update(name='Changed', price=2)

    return await client.request(
        'POST' if operation == 'delete' else operation.upper(),
        path + ('/delete' if operation == 'delete' else ''),
        json=body,
    )


@pytest.mark.parametrize('operation', ['patch', 'put', 'delete'])
@pytest.mark.parametrize('version', [None, True, False, '1', 0, -1, 1.5, 4294967296])
async def test_invalid_preconditions_preserve_item(
    client: httpx.AsyncClient, operation: str, version: object
) -> None:
    item = await create_item(client)
    path = ITEMS_URL + item['id']
    response = await mutate(client, path, operation, version)

    assert response.status_code == 422
    assert 'expected_version' in response.json()['message']
    assert (await client.get(path)).json() == item


@pytest.mark.parametrize('operation', ['patch', 'put', 'delete'])
async def test_missing_precondition_is_rejected(
    client: httpx.AsyncClient, operation: str
) -> None:
    item = await create_item(client)
    path = ITEMS_URL + item['id']
    response = await client.request(
        'POST' if operation == 'delete' else operation.upper(),
        path + ('/delete' if operation == 'delete' else ''),
        json={'name': 'Changed', 'price': 2},
    )

    assert response.status_code == 422
    assert (await client.get(path)).json() == item


@pytest.mark.parametrize('operation', ['patch', 'put', 'delete'])
async def test_stale_and_missing_resources_have_distinct_errors(
    client: httpx.AsyncClient, operation: str
) -> None:
    item = await create_item(client)
    path = ITEMS_URL + item['id']
    changed = await mutate(client, path, 'patch')

    assert changed.status_code == 200 and changed.json()['version'] == 2
    stale = await mutate(client, path, operation)

    assert stale.status_code == 409 and stale.json()['message'] == CONFLICT
    assert (await client.get(path)).json() == changed.json()
    missing = await mutate(client, ITEMS_URL + MISSING_ID, operation)

    assert missing.status_code == 404
    assert missing.json()['message'] == 'No item exists with the provided identifier.'


@pytest.mark.parametrize('operation', ['patch', 'put'])
async def test_unchanged_values_increment_once_and_retries_conflict(
    client: httpx.AsyncClient, operation: str
) -> None:
    item = await create_item(client, 'Changed', 2)
    path = ITEMS_URL + item['id']
    accepted = await mutate(client, path, operation, 1.0)

    assert accepted.status_code == 200 and accepted.json()['version'] == 2
    assert (await mutate(client, path, operation)).status_code == 409
    assert (await client.get(path)).json() == accepted.json()


async def test_patch_requires_an_edit_and_delete_returns_final_revision(
    client: httpx.AsyncClient,
) -> None:
    item = await create_item(client)
    path = ITEMS_URL + item['id']

    for body in (
        {'expected_version': 1},
        {'expected_version': 1, 'unknown': 'ignored'},
    ):
        assert (await client.patch(path, json=body)).status_code == 422

    changed = await mutate(client, path, 'put')
    removed = await mutate(client, path, 'delete', 2)

    assert removed.status_code == 200 and removed.json() == changed.json()
    assert (await mutate(client, path, 'delete', 2)).status_code == 404


@pytest.mark.parametrize('operation', ['patch', 'put'])
async def test_revision_overflow_preserves_values_but_final_revision_can_be_deleted(
    client: httpx.AsyncClient, database_engine: AsyncEngine, operation: str
) -> None:
    item = await create_item(client)
    path = ITEMS_URL + item['id']

    async with database_engine.begin() as connection:
        await connection.execute(
            update(ItemORM).where(ItemORM.id == item['id']).values(version=4294967295)
        )

    before = (await client.get(path)).json()
    response = await mutate(client, path, operation, 4294967295)

    assert response.status_code == 409 and response.json()['message'] == CONFLICT
    assert (await client.get(path)).json() == before
    removed = await mutate(client, path, 'delete', 4294967295)

    assert removed.status_code == 200 and removed.json() == before


@pytest.mark.parametrize(
    'operations',
    [('patch', 'patch'), ('put', 'patch'), ('patch', 'delete'), ('delete', 'delete')],
)
async def test_concurrent_mutations_serialize_without_lost_writes(
    client: httpx.AsyncClient,
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    operations: tuple[str, str],
) -> None:
    item = await create_item(client)
    path = ITEMS_URL + item['id']
    arrived = asyncio.Event()
    sessions: set[AsyncSession] = set()
    original = repo.get_by_id_for_update

    async def lock(session: AsyncSession, id: str) -> ItemORM | None:
        sessions.add(session)
        if len(sessions) == 2:
            arrived.set()

        return await original(session, id)

    monkeypatch.setattr(repo, 'get_by_id_for_update', lock)
    factory = async_sessionmaker(database_engine)
    tasks: list[asyncio.Task[httpx.Response]] = []

    try:
        async with factory() as blocker, blocker.begin():
            await blocker.execute(
                select(ItemORM).where(ItemORM.id == item['id']).with_for_update()
            )
            tasks = [
                asyncio.create_task(mutate(client, path, operation))
                for operation in operations
            ]

            async with asyncio.timeout(3):
                await arrived.wait()

        async with asyncio.timeout(5):
            responses = await asyncio.gather(*tasks)

        assert sum(response.status_code == 200 for response in responses) == 1
        winner = next(
            index
            for index, response in enumerate(responses)
            if response.status_code == 200
        )
        loser = responses[1 - winner]

        assert loser.status_code == (404 if operations[winner] == 'delete' else 409)
        fetched = await client.get(path)

        if operations[winner] == 'delete':
            assert fetched.status_code == 404
            assert responses[winner].json() == item
        else:
            assert fetched.json() == responses[winner].json()
            assert fetched.json()['version'] == 2
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)


async def test_canonical_routes_and_old_delete_removal(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        '/api/v1/items', json={'name': 'Alias', 'price': 1, 'version': 99}
    )

    assert response.status_code == 201 and not response.history
    item = response.json()

    assert item['version'] == 1
    for path in ('/api/v1/items', '/api/v1/items/'):
        listing = await client.get(path)

        assert listing.status_code == 200 and not listing.history
        assert listing.json()['data'] == [item]

    assert (await client.delete(ITEMS_URL + item['id'])).status_code == 405
    assert (await client.get(ITEMS_URL + item['id'])).json() == item


@pytest.mark.parametrize('suffix', ['', '/'])
async def test_flexible_mutation_routes_keep_transactions_and_versions(
    client: httpx.AsyncClient, suffix: str
) -> None:
    created = await client.post(
        '/api/v1/items' + suffix,
        json={'name': 'Flexible', 'price': 1},
        follow_redirects=False,
    )

    assert created.status_code == 201
    path = ITEMS_URL + created.json()['id']

    for method, body, version in [
        ('PATCH', {'name': 'Patched', 'expected_version': 1}, 2),
        ('PUT', {'name': 'Replaced', 'price': 2, 'expected_version': 2}, 3),
    ]:
        response = await client.request(
            method, path + suffix, json=body, follow_redirects=False
        )

        assert response.status_code == 200 and response.json()['version'] == version
        fetched = await client.get(path + suffix, follow_redirects=False)

        assert fetched.status_code == 200 and fetched.json() == response.json()

    removed = await client.post(
        path + '/delete' + suffix, json={'expected_version': 3}, follow_redirects=False
    )

    assert removed.status_code == 200 and removed.json()['version'] == 3
    assert (await client.get(path)).status_code == 404
