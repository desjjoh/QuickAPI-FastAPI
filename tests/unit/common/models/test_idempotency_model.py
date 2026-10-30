import json
from decimal import Decimal

import pytest
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr
from starlette.requests import Request

from app.common.handlers.application_route import ApplicationRoute
from app.common.models.idempotency_model import (
    IdempotencyPolicy,
    digest,
    idempotent,
    read_key,
)
from app.common.services.idempotency_service import (
    PreparedJSONResponse,
    validate_response,
)

pytestmark = pytest.mark.unit


def request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({'type': 'http', 'headers': headers})


def test_key_is_optional_opaque_and_case_sensitive() -> None:
    assert read_key(request([])) is None
    assert read_key(request([(b'idempotency-key', b'AbC-123')])) == 'AbC-123'
    assert digest(['AbC']) != digest(['abc'])


@pytest.mark.parametrize(
    'values', [[b'a', b'a'], [b''], [b'a,b'], [b'a b'], [b'\x7f'], [b'x' * 129]]
)
def test_duplicate_and_malformed_raw_keys_are_rejected(values: list[bytes]) -> None:
    with pytest.raises(HTTPException) as error:
        read_key(request([(b'idempotency-key', value) for value in values]))

    assert error.value.status_code == 400


def test_fingerprints_normalize_models_and_object_order_but_retain_missing_fields() -> (
    None
):
    class Body(BaseModel):
        name: str
        description: str | None = None
        multiplier: int = 1

    assert digest({'body': Body(name='Item'), 'query': None}) == digest(
        {'query': None, 'body': {'name': 'Item', 'multiplier': 1}}
    )
    assert digest(Body(name='Item')) != digest(Body(name='Item', description=None))
    assert digest(Body(name='Item')) == digest(Body(name='Item', multiplier=1))
    assert digest({'number': 1}) == digest({'number': 1.0})
    with pytest.raises(ValueError):
        digest(float('nan'))


def test_prepared_response_is_not_serialized_again() -> None:
    body = b'{ "value" : 1, "unicode": "\\u00e9" }'
    response = PreparedJSONResponse(body, 201)

    assert response.body == body and response.status_code == 201
    assert response.headers['content-type'] == 'application/json'
    assert json.loads(bytes(response.body))['value'] == 1
    validate_response(201, body, len(body))
    validate_response(204, b'', 1)
    for status, value in [
        (500, b'{}'),
        (204, b'{}'),
        (201, b'not JSON'),
        (201, b'{"value":NaN}'),
        (201, body + b' '),
    ]:
        with pytest.raises((ValueError, RuntimeError)):
            validate_response(status, value, len(body))


def test_fingerprints_use_real_secret_and_excluded_input_values() -> None:
    class Credentials(BaseModel):
        password: SecretStr
        private_input: str = Field(exclude=True)

    original = Credentials(password=SecretStr('test-first'), private_input='one')
    changed_secret = Credentials(password=SecretStr('test-second'), private_input='one')
    changed_excluded = Credentials(
        password=SecretStr('test-first'), private_input='two'
    )

    assert original.model_dump(mode='json') == changed_secret.model_dump(mode='json')
    assert original.model_dump(mode='json') == changed_excluded.model_dump(mode='json')
    assert (
        len({digest(original), digest(changed_secret), digest(changed_excluded)}) == 3
    )


def test_decimal_fingerprints_preserve_precision_and_numeric_equivalence() -> None:
    assert digest(Decimal('12.3400')) == digest(12.34)
    assert digest(Decimal('1.0')) == digest(1)
    assert digest(Decimal('-0.00')) == digest(0.0)
    assert digest(Decimal('0.123456789123456789')) != digest(
        Decimal('0.123456789123456788')
    )
    assert digest(Decimal('1e100000')) == digest(Decimal('10e99999'))
    with pytest.raises(ValueError):
        digest(Decimal('NaN'))


def test_invalid_declarations_fail_when_routes_are_registered() -> None:
    for operation, route in [
        ('', '/domain'),
        ('x' * 129, '/domain'),
        ('domain.create', ''),
    ]:
        with pytest.raises(ValueError):
            IdempotencyPolicy(operation, route, "public")

    router = APIRouter(route_class=ApplicationRoute)

    with pytest.raises(RuntimeError, match='transactional'):

        @router.post('/unowned')
        @idempotent(
            operation='other.create', route='POST /unowned', caller_scope="public"
        )
        async def unowned() -> dict[str, bool]:
            return {'ok': True}
