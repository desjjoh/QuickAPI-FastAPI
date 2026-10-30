import copy
import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict

import pytest
from fastapi import Body, Depends, Header, Query, Request
from pydantic import BaseModel, Field, SecretStr, TypeAdapter
from starlette.requests import HTTPConnection

from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.models.idempotency_model import FINGERPRINT_FORMAT, digest, idempotent
from app.config.database import get_session

pytestmark = pytest.mark.unit


class Vector(TypedDict):
    name: str
    input: dict[str, Any]
    canonical: str
    sha256: str
    decimal_paths: list[list[str]]


class Reference(TypedDict):
    format: str
    vectors: list[Vector]


reference = TypeAdapter[Reference](Reference).validate_json(
    (
        Path(__file__).resolve().parents[3]
        / 'fixtures'
        / 'idempotency_fingerprints_v1.json'
    ).read_bytes()
)


@pytest.mark.parametrize(
    'vector',
    reference['vectors'],
    ids=[vector['name'] for vector in reference['vectors']],
)
def test_frozen_v1_fingerprint_vectors(vector: Vector) -> None:
    assert FINGERPRINT_FORMAT == reference['format'] == 'quickapi-json-v1'
    assert (
        hashlib.sha256(vector['canonical'].encode('utf-8')).hexdigest()
        == vector['sha256']
    )
    value = copy.deepcopy(vector['input'])

    for path in vector['decimal_paths']:
        target = value

        for key in path[:-1]:
            target = target[key]

        target[path[-1]] = Decimal(target[path[-1]])

    assert digest(value) == vector['sha256']


def test_validated_models_match_frozen_v1_vectors() -> None:
    class Item(BaseModel):
        name: str
        price: Decimal
        description: str | None = None

    class Credentials(BaseModel):
        password: SecretStr
        private_input: str = Field(exclude=True)

    expected = {vector['name']: vector['sha256'] for vector in reference['vectors']}

    for name, body in [
        ('optional-omitted', Item(name='Item', price=Decimal('12.3400'))),
        ('optional-null', Item(name='Item', price=Decimal('12.34'), description=None)),
        (
            'secret-fields',
            Credentials(password=SecretStr('test-first'), private_input='one'),
        ),
    ]:
        assert digest({'body': body, 'params': None, 'query': None}) == expected[name]


class Input(BaseModel):
    value: int


def keyed(endpoint: Any) -> Any:
    return transactional(
        idempotent(
            operation='widgets.create', route='POST /widgets/:id', caller_scope='public'
        )(endpoint)
    )


@pytest.mark.parametrize('kind', ['body', 'path', 'query'])
def test_hidden_dependency_inputs_fail_at_registration(kind: str) -> None:
    def body_input(payload: Input) -> object:
        return payload

    def path_input(id: int) -> object:
        return id

    def query_input(value: int = Query(1)) -> object:
        return value

    inner = {'body': body_input, 'path': path_input, 'query': query_input}[kind]

    def outer(value: object = Depends(inner)) -> object:
        return value

    async def endpoint(id: int, value: object = Depends(outer)) -> dict[str, bool]:
        return {'ok': True}

    with pytest.raises(RuntimeError, match='declared directly on the endpoint'):
        ApplicationRoute('/widgets/{id}', keyed(endpoint), methods=['POST'])


@pytest.mark.parametrize(
    'kind', ['request', 'connection', 'header', 'missing-path', 'non-json']
)
def test_uncaptured_direct_inputs_fail_at_registration(kind: str) -> None:
    async def raw_request(request: Request) -> dict[str, bool]:
        return {'ok': True}

    async def raw_connection(connection: HTTPConnection) -> dict[str, bool]:
        return {'ok': True}

    async def raw_header(locale: str = Header('en')) -> dict[str, bool]:
        return {'ok': True}

    async def missing_path(payload: Input) -> dict[str, bool]:
        return {'ok': True}

    async def non_json(payload: str = Body(media_type='text/plain')) -> dict[str, bool]:
        return {'ok': True}

    endpoint = {
        'request': raw_request,
        'connection': raw_connection,
        'header': raw_header,
        'missing-path': missing_path,
        'non-json': non_json,
    }[kind]

    with pytest.raises(RuntimeError):
        ApplicationRoute(
            '/widgets/{id}' if kind == 'missing-path' else '/widgets',
            keyed(endpoint),
            methods=['POST'],
        )


def test_direct_inputs_with_authorization_and_service_dependencies_are_supported() -> (
    None
):
    def authenticate(request: Request, token: str = Header('test')) -> str:
        return token

    async def endpoint(
        id: int,
        payload: Input,
        page: int = Query(1),
        actor: str = Depends(authenticate),
        session: object = Depends(get_session),
    ) -> dict[str, bool]:
        return {'ok': True}

    route = ApplicationRoute('/widgets/{id}', keyed(endpoint), methods=['POST'])

    assert route.endpoint is endpoint
