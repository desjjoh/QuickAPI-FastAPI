import inspect
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.handlers.application_route import (
    TRANSACTION_SESSION_KEY,
    ApplicationRoute,
    transactional,
)
from app.config import database

pytestmark = pytest.mark.unit


async def endpoint(value: int = 1) -> dict[str, int]:
    return {'value': value}


def test_marker_preserves_endpoint_and_dependency_signature() -> None:
    signature = inspect.signature(endpoint)
    assert transactional(endpoint) is endpoint
    assert inspect.signature(endpoint) == signature


async def test_route_rejects_existing_owner_before_allocating_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock(side_effect=AssertionError('Must not allocate another session'))
    monkeypatch.setattr(database, 'SessionLocal', factory)
    route = ApplicationRoute(
        '/test', endpoint=transactional(endpoint), methods=['POST']
    )
    request = Request({'type': 'http', TRANSACTION_SESSION_KEY: None})
    with pytest.raises(RuntimeError, match='already owns'):
        await route.get_route_handler()(request)
    factory.assert_not_called()


async def test_route_rejects_an_already_active_factory_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncSession(autobegin=False)
    await session.begin()
    monkeypatch.setattr(database, 'SessionLocal', Mock(return_value=session))
    route = ApplicationRoute(
        '/test', endpoint=transactional(endpoint), methods=['POST']
    )
    request = Request({'type': 'http'})
    with pytest.raises(RuntimeError, match='fresh transaction owner'):
        await route.get_route_handler()(request)
    assert not session.in_transaction()
    assert TRANSACTION_SESSION_KEY not in request.scope


async def test_dependency_borrows_without_closing_owner_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncSession()
    close = AsyncMock()
    monkeypatch.setattr(session, 'close', close)
    factory = Mock(side_effect=AssertionError('Must borrow instead'))
    monkeypatch.setattr(database, 'SessionLocal', factory)
    dependency = database.get_session(
        Request({'type': 'http', TRANSACTION_SESSION_KEY: session})
    )
    assert await anext(dependency) is session
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    close.assert_not_awaited()
    factory.assert_not_called()


async def test_dependency_rejects_invalid_owner() -> None:
    dependency = database.get_session(
        Request({'type': 'http', TRANSACTION_SESSION_KEY: object()})
    )
    with pytest.raises(RuntimeError, match='Invalid mutation'):
        await anext(dependency)


async def test_native_response_options_and_schema_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def factory(**kwargs: object) -> AsyncSession:
        assert kwargs == {'autobegin': False}
        return AsyncSession(autobegin=False)

    monkeypatch.setattr(database, 'SessionLocal', factory)
    router = APIRouter(route_class=ApplicationRoute)

    class Projection(BaseModel):
        name: str = Field(alias='display_name')
        optional: str | None = None

    # Keep the local model in response_model rather than a forward annotation.
    @router.post(
        '/prepared',
        response_model=Projection,
        status_code=201,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    @transactional
    async def prepared() -> object:
        return Projection(display_name='Prepared')

    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        response = await client.post('/prepared')
    assert response.status_code == 201
    assert response.content == b'{"display_name":"Prepared"}'
    assert response.headers['content-length'] == str(len(response.content))
    assert '201' in app.openapi()['paths']['/prepared']['post']['responses']


async def test_unmarked_route_does_not_allocate_a_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock(
        side_effect=AssertionError('Read route must not open a mutation transaction')
    )
    monkeypatch.setattr(database, 'SessionLocal', factory)
    router = APIRouter(route_class=ApplicationRoute)

    @router.get('/read')
    async def read() -> dict[str, bool]:
        return {'done': True}

    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        assert (await client.get('/read')).json() == {'done': True}
    factory.assert_not_called()
