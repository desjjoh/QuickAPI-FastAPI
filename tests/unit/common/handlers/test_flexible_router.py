import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.types import Message, Scope

from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.handlers.flexible_router import (
    FlexibleRouter,
    HeadResponseASGIMiddleware,
)

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
        for path in ('/api/items', '/api/items/', '/API/ITEMS', '/Api/Items/'):
            response = await client.post(path, json={'value': 7})

            assert response.status_code == 201 and response.json() == {'value': 7}
            assert 'location' not in response.headers

    assert calls == ['dependency', 'handler'] * 4


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


@pytest.mark.parametrize('explicit_head', [False, True])
async def test_head_fallback_and_explicit_handler_preserve_nested_routes(
    explicit_head: bool,
) -> None:
    router = FlexibleRouter(route_class=ApplicationRoute)
    calls: list[tuple[str, str]] = []

    @router.get('/records/{record_id}', response_model=Payload)
    async def read(
        record_id: str, request: Request, response: Response
    ) -> dict[str, object]:
        calls.append((request.method, record_id))
        response.headers['x-handler'] = 'get'

        return {'value': 7, 'private': 'excluded'}

    if explicit_head:

        @router.head('/records/{record_id}', include_in_schema=False)
        async def head(record_id: str, response: Response) -> None:
            calls.append(('explicit', record_id))
            response.headers['x-handler'] = 'head'

    parent = APIRouter(prefix='/v1')

    parent.include_router(router)
    app = FastAPI()

    app.include_router(parent, prefix='/api')

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url='http://test'
    ) as client:
        result = await client.get('/API/V1/Records/AbCd/')

        assert result.json() == {'value': 7}

        for path in ['/api/v1/records/AbCd', '/API/V1/RECORDS/AbCd/']:
            result = await client.head(path)

            assert result.status_code == 200 and result.content == b''
            assert result.headers['x-handler'] == ('head' if explicit_head else 'get')

    assert (
        calls
        == [('GET', 'AbCd')] + [('explicit' if explicit_head else 'HEAD', 'AbCd')] * 2
    )
    assert set(app.openapi()['paths']['/api/v1/records/{record_id}']) == {'get'}


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
@pytest.mark.parametrize('status', [200, 404, 500])
async def test_head_transport_suppresses_success_and_error_bodies(
    method: str,
    status: int,
) -> None:
    response = Response(
        'representation', status_code=status, headers={'x-marker': 'kept'}
    )
    scope: Scope = {'type': 'http', 'method': method, 'path': '/', 'headers': []}
    sent: list[Message] = []

    async def receive() -> Message:
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        sent.append(message)

    await HeadResponseASGIMiddleware(response)(scope, receive, send)

    assert sent[0]['status'] == status
    assert (b'content-length', b'14') in sent[0]['headers']
    assert (b'x-marker', b'kept') in sent[0]['headers']
    assert sent[1]['body'] == (b'' if method == 'HEAD' else b'representation')
