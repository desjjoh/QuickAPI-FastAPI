import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.v1.items.models.item_model import ItemBase, ItemResponse
from app.api.v1.items.services.item_service import ItemService, get_item_service
from app.common.handlers.application_route import ApplicationRoute, transactional
from app.config import database
from app.config.application import create_app
from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import ItemCreateData, repo

pytestmark = pytest.mark.integration


async def test_concurrent_mutations_keep_transaction_owners_isolated(
    database_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    monkeypatch.setattr(database, 'SessionLocal', factory)
    original_create = repo.create
    sessions: set[AsyncSession] = set()
    both_written = asyncio.Event()

    async def create(session: AsyncSession, *, item_in: ItemCreateData) -> ItemORM:
        item = await original_create(session, item_in=item_in)

        sessions.add(session)
        if len(sessions) == 2:
            both_written.set()

        async with asyncio.timeout(5):
            await both_written.wait()

        if item_in['name'] == 'Rollback':
            raise RuntimeError('Injected failure after concurrent writes')

        return item

    monkeypatch.setattr(repo, 'create', create)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_app(), raise_app_exceptions=False),
        base_url='http://test',
    ) as client:
        committed, rejected = await asyncio.gather(
            client.post('/api/v1/items/', json={'name': 'Committed', 'price': 1}),
            client.post('/api/v1/items/', json={'name': 'Rollback', 'price': 2}),
        )

    assert committed.status_code == 201 and rejected.status_code == 500
    assert len(sessions) == 2 and all(
        not session.in_transaction() for session in sessions
    )
    async with factory() as observer:
        assert list(await observer.scalars(select(ItemORM.name))) == ['Committed']


@pytest_asyncio.fixture
async def transaction_client(
    database_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(
        database,
        'SessionLocal',
        async_sessionmaker(database_engine, expire_on_commit=False, autoflush=False),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_app(), raise_app_exceptions=False),
        base_url='http://test',
    ) as client:
        yield client


CASES: list[tuple[str, str]] = [
    (method, failure)
    for method in ['POST', 'PATCH', 'PUT', 'DELETE']
    for failure in ['flush', 'refresh', 'model', 'response_model', 'render', 'commit']
    if method != 'DELETE' or failure != 'refresh'
]


@pytest.mark.parametrize('method,failure', CASES)
async def test_mutation_preparation_and_precommit_failures_roll_back_mysql(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    failure: str,
) -> None:
    factory = async_sessionmaker(
        database_engine, expire_on_commit=False, autoflush=False
    )

    async with factory() as seed, seed.begin():
        before = ItemORM(name='Before', price=Decimal('1'), description='Original')

        seed.add(before)
        await seed.flush()
        identifier = before.id

    owned: list[AsyncSession] = []
    rejected_writes: list[IntegrityError] = []

    def session_factory(**kwargs: Any) -> AsyncSession:
        session = factory(**kwargs)

        owned.append(session)
        if failure == 'commit':

            def fail_before_commit(*_: object) -> None:
                raise RuntimeError('private precommit failure')

            event.listen(session.sync_session, 'before_commit', fail_before_commit)

        if failure in {'flush', 'refresh'}:
            original = getattr(session, failure)

            async def fail(*args: Any, **values: Any) -> None:
                await original(*args, **values)
                if failure == 'flush':
                    # MySQL must reject a real statement after the preceding
                    # mutation wrote successfully. The owner must undo that write.
                    try:
                        await session.execute(
                            text(
                                "INSERT INTO items (id,name,price) VALUES ('write-failure',NULL,1)"
                            )
                        )
                    except IntegrityError as error:
                        rejected_writes.append(error)

                        raise

                raise RuntimeError('private database preparation failure')

            monkeypatch.setattr(session, failure, fail)

        return session

    monkeypatch.setattr(database, 'SessionLocal', session_factory)
    if failure in {'model', 'response_model'}:

        def invalid_model(cls: type[ItemResponse], value: object) -> Any:
            if failure == 'model':
                raise ValueError('private DTO validation failure')

            return {'id': 'invalid'}

        monkeypatch.setattr(ItemResponse, 'model_validate', classmethod(invalid_model))

    if failure == 'render':
        original_render = JSONResponse.render

        def invalid_render(self: JSONResponse, content: Any) -> bytes:
            if isinstance(content, dict) and 'id' in content and 'name' in content:
                raise ValueError('private JSON rendering failure')

            return original_render(self, content)

        monkeypatch.setattr(JSONResponse, 'render', invalid_render)

    app = create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, raise_app_exceptions=False),
        base_url='http://test',
    ) as client:
        path = '/api/v1/items/' if method == 'POST' else f'/api/v1/items/{identifier}'
        payload = None if method == 'DELETE' else {'name': 'After', 'price': 2.5}
        response = await client.request(method, path, json=payload)

    assert response.status_code == 500
    assert response.json()['message'] == 'Internal server error.'
    assert 'private' not in response.text
    assert len(owned) == 1 and not owned[0].in_transaction()
    if failure == 'flush':
        assert len(rejected_writes) == 1
        cause = rejected_writes[0].orig

        assert cause is not None and cause.args[0] == 1048

    # An observer must use a separate session/transaction, not an identity-map view.
    async with factory() as observer:
        rows = list(
            (
                await observer.execute(
                    select(ItemORM.name, ItemORM.price, ItemORM.description)
                )
            ).all()
        )

        assert [(row[0], float(row[1]), row[2]) for row in rows] == [
            ('Before', 1.0, 'Original')
        ]


async def test_transactional_crud_preserves_status_and_response_contract(
    transaction_client: httpx.AsyncClient,
) -> None:
    client = transaction_client
    created = await client.post(
        '/api/v1/items/', json={'name': 'Created', 'price': 2.5}
    )

    assert created.status_code == 201
    first = created.json()

    assert set(first) == {
        'id',
        'name',
        'description',
        'price',
        'createdAt',
        'updatedAt',
    }
    path = '/api/v1/items/' + first['id']
    patched = await client.patch(path, json={'description': 'Changed'})

    assert patched.status_code == 200 and patched.json()['name'] == 'Created'
    replaced = await client.put(path, json={'name': 'Replaced', 'price': 3})

    assert replaced.status_code == 200 and replaced.json()['description'] is None
    assert (await client.get(path)).json() == replaced.json()
    deleted = await client.delete(path)

    assert deleted.status_code == 200 and deleted.json() == replaced.json()
    assert (await client.get(path)).status_code == 404


@pytest.mark.parametrize('method', ['PATCH', 'PUT', 'DELETE'])
async def test_missing_mutation_keeps_404_contract(
    transaction_client: httpx.AsyncClient, method: str
) -> None:
    response = await transaction_client.request(
        method,
        '/api/v1/items/' + '0' * 16,
        json=None if method == 'DELETE' else {'name': 'Absent', 'price': 1},
    )

    assert response.status_code == 404
    assert (
        response.json()['message'] == "Resource with ID '0000000000000000' not found."
    )


@pytest.mark.parametrize('kind', ['stream', 'background', 'error'])
async def test_transaction_route_rejects_deferred_work_and_rolls_back_error_responses(
    database_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    monkeypatch.setattr(database, 'SessionLocal', factory)
    ran: list[str] = []
    router = APIRouter(route_class=ApplicationRoute)

    @router.post('/transaction-test')
    @transactional
    async def operation(db: AsyncSession = Depends(database.get_session)) -> Response:
        await repo.create(db, item_in={'name': 'Discarded', 'price': Decimal('1')})
        if kind == 'stream':

            async def stream() -> AsyncIterator[bytes]:
                ran.append('stream')
                yield b'late'

            return StreamingResponse(stream())

        if kind == 'background':
            tasks = BackgroundTasks()

            tasks.add_task(ran.append, 'background')

            return JSONResponse({'done': True}, background=tasks)

        return JSONResponse({'message': 'Rejected'}, status_code=409)

    app = create_app()

    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, raise_app_exceptions=False),
        base_url='http://test',
    ) as client:
        response = await client.post('/transaction-test', json={})

    assert response.status_code == (409 if kind == 'error' else 500)
    assert ran == []
    async with factory() as observer:
        assert list(await observer.scalars(select(ItemORM.id))) == []


async def test_dependencies_share_one_owner_and_cannot_autobegin_after_commit(
    database_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    monkeypatch.setattr(database, 'SessionLocal', factory)
    sessions: list[AsyncSession] = []
    router = APIRouter(route_class=ApplicationRoute)

    @router.post('/session-test')
    @transactional
    async def operation(
        first: AsyncSession = Depends(database.get_session),
        second: AsyncSession = Depends(database.get_session, use_cache=False),
        service: ItemService = Depends(get_item_service),
    ) -> dict[str, bool]:
        assert service.db is first is second and first.in_transaction()
        sessions.append(first)
        await service.create(
            ItemBase(name='Committed', price=Decimal('1'), description=None)
        )

        return {'done': True}

    app = create_app()

    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        assert (await client.post('/session-test', json={})).status_code == 200

    assert not sessions[0].in_transaction()
    with pytest.raises(InvalidRequestError, match=r'autobegin|Autobegin'):
        await sessions[0].execute(select(ItemORM.id))

    async with factory() as observer:
        assert list(await observer.scalars(select(ItemORM.name))) == ['Committed']
