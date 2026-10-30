import json
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from app.api.v1.items.models.item_model import ItemBase, ItemResponse
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.api.v1.items.models.pagination_query_model import ItemPaginationQuery
from app.common.models.converter import model_to
from app.common.models.price_model import Price
from app.database.entities import base_orm
from app.database.repositories.item_repo import ItemCreateData

pytestmark = pytest.mark.unit
adapter = TypeAdapter[Decimal](Price)

VALID_PRICES: list[object] = [
    0.01,
    1,
    1.2,
    99999999.99,
    '0.01',
    '1',
    '1.2',
    '01.20',
    '00000099.99',
    Decimal('1.2300'),
    1e2,
    1e-2,
]
INVALID_PRICES: list[object] = [
    None,
    True,
    False,
    [],
    {},
    b'1.23',
    0,
    -1,
    0.001,
    0.009,
    100000000,
    1.001,
    0.1 + 0.2,
    float('nan'),
    float('inf'),
    -float('inf'),
    '',
    ' 1',
    '1 ',
    '+1',
    '-1',
    '1e2',
    '1.',
    '.01',
    '1.230',
    'NaN',
    'Infinity',
    '1_000',
    '\uff11\uff12.\uff13\uff14',
    '1.00\n',
    Decimal('sNaN'),
    Decimal('1e100'),
    Decimal('1.000000000000000000000001'),
]


@pytest.mark.parametrize('value', VALID_PRICES)
def test_price_is_exact_decimal_in_python_and_number_in_json(value: object) -> None:
    price = adapter.validate_python(value)

    assert isinstance(price, Decimal)
    assert price == Decimal(str(value))
    assert price.as_tuple().exponent == -2
    assert isinstance(adapter.dump_python(price), Decimal)
    encoded = json.loads(adapter.dump_json(price))

    assert isinstance(encoded, (float, int)) and not isinstance(encoded, bool)
    assert Decimal(str(encoded)) == price


@pytest.mark.parametrize('value', INVALID_PRICES)
def test_invalid_prices_are_rejected_without_rounding(value: object) -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


@pytest.mark.parametrize('value', [0, '1.234', True, '1e2', ' 1.2', 100000000])
def test_all_input_models_share_the_price_contract(value: object) -> None:
    for model, payload in [
        (ItemBase, {'name': 'Item', 'price': value}),
        (UpdateItemRequest, {'price': value}),
        (ItemPaginationQuery, {'min_price': value}),
        (ItemPaginationQuery, {'max_price': value}),
    ]:
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_decimal_context_cannot_change_validation_or_accepted_amount() -> None:
    with localcontext() as context:
        context.prec = 2

        assert adapter.validate_python('99999999.99') == Decimal('99999999.99')
        with pytest.raises(ValidationError):
            adapter.validate_python(Decimal('1.000000000000000000000001'))


def test_repository_conversion_keeps_decimal_values() -> None:
    payload = ItemBase.model_validate({'name': 'Item', 'price': '12.34'})
    data = model_to(ItemCreateData, payload)

    assert data['price'] == Decimal('12.34')
    assert isinstance(data['price'], Decimal)


def test_response_aliases_preserve_python_attributes_and_validate_prices() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    item = SimpleNamespace(
        id='A1b2C3d4E5f6G7h8',
        name='Item',
        price=Decimal('12.34'),
        description=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    response = ItemResponse.model_validate(item)

    assert response.created_at == response.updated_at == timestamp
    assert isinstance(response.price, Decimal)
    body = json.loads(response.model_dump_json())

    assert set(body) == {'id', 'name', 'price', 'description', 'createdAt', 'updatedAt'}
    assert body['price'] == 12.34 and isinstance(body['price'], float)
    assert ItemResponse.model_validate(body) == response
    item.price = Decimal('1.234')

    with pytest.raises(ValidationError):
        ItemResponse.model_validate(item)


def test_id_generator_uses_sixteen_secure_alphanumeric_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter('A1b2C3d4E5f6G7h8')
    calls: list[str] = []

    def choose(alphabet: str) -> str:
        calls.append(alphabet)

        return next(values)

    monkeypatch.setattr(base_orm, 'choice', choose)
    assert base_orm.generate_id() == 'A1b2C3d4E5f6G7h8'
    assert len(calls) == 16
    assert all(
        set(alphabet)
        == set('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
        for alphabet in calls
    )
