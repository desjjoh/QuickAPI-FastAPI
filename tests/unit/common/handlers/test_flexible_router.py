import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.handlers.flexible_router import FlexibleRouter

pytestmark = pytest.mark.unit


class Payload(BaseModel):
    value: int


@pytest.mark.parametrize('flexible_parent', [False, True])
async def test_nested_inclusion_preserves_options_without_duplicate_aliases(
    flexible_parent: bool,
) -> None:
    child = FlexibleRouter(route_class=ApplicationRoute)
    calls: list[str] = []

    async def dependency() -> None:
        calls.append('dependency')

    @child.post(
        '',
        response_model=Payload,
        status_code=201,
        dependencies=[Depends(dependency)],
        name='create',
        tags=['Items'],
    )
    async def create(payload: Payload) -> dict[str, object]:
        calls.append('handler')

        return {'value': payload.value, 'private': 'excluded'}

    parent = FlexibleRouter() if flexible_parent else APIRouter()

    parent.include_router(child, prefix='/items')
    outer = FlexibleRouter(prefix='/api')

    outer.include_router(parent)
    app = FastAPI()

    app.include_router(outer)
    routes = [route for route in app.routes if isinstance(route, APIRoute)]

    assert len(routes) == 2
    assert all(
        isinstance(route, ApplicationRoute) and route.endpoint is create
        for route in routes
    )
    assert str(app.url_path_for('create')) == '/api/items'
    schema = app.openapi()

    assert set(schema['paths']) == {'/api/items'}
    assert schema['paths']['/api/items']['post']['tags'] == ['Items']
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url='http://test',
        follow_redirects=False,
    ) as client:
        for path in ('/api/items', '/api/items/'):
            response = await client.post(path, json={'value': 7})

            assert response.status_code == 201 and response.json() == {'value': 7}
            assert 'location' not in response.headers

    assert calls == ['dependency', 'handler', 'dependency', 'handler']


async def test_explicit_root_remains_single_and_resource_slash_is_normalized() -> None:
    router = FlexibleRouter()

    @router.get('/')
    async def root() -> dict[str, bool]:
        return {'root': True}

    @router.get('/resource/')
    async def resource() -> dict[str, bool]:
        return {'root': False}

    app = FastAPI()

    app.include_router(router)
    assert set(app.openapi()['paths']) == {'/', '/resource'}
    assert len([route for route in app.routes if isinstance(route, APIRoute)]) == 3
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url='http://test',
        follow_redirects=False,
    ) as client:
        for path in ('/', '/resource', '/resource/'):
            assert (await client.get(path)).status_code == 200


def test_transaction_marker_and_hidden_routes_survive_inclusion() -> None:
    router = FlexibleRouter(route_class=ApplicationRoute)

    @router.post('/resource', include_in_schema=False)
    @transactional
    async def operation() -> dict[str, bool]:
        return {'ok': True}

    app = FastAPI()

    app.include_router(router)
    routes = [route for route in app.routes if isinstance(route, APIRoute)]

    assert len(routes) == 2
    assert all(
        route.endpoint is operation and isinstance(route, ApplicationRoute)
        for route in routes
    )
    assert not app.openapi()['paths']
