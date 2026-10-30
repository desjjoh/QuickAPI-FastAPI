import re
from collections.abc import AsyncGenerator
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import database
from app.config.application import create_app
from app.database.entities.item_orm import ItemORM

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def contract_client(
    database_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[httpx.AsyncClient, None]:
    monkeypatch.setattr(
        database,
        'SessionLocal',
        async_sessionmaker(database_engine, expire_on_commit=False),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_app(), raise_app_exceptions=False),
        base_url='http://test',
    ) as client:
        yield client


@pytest.mark.parametrize(
    'price', [0.01, 1, 12.34, 99999999.99, '0.01', '00012.34', '99999999.99']
)
async def test_price_round_trip_is_exact_in_mysql_and_numeric_on_the_wire(
    database_engine: AsyncEngine,
    contract_client: httpx.AsyncClient,
    price: float | str,
) -> None:
    response = await contract_client.post(
        '/api/v1/items/', json={'name': 'Exact', 'price': price}
    )

    assert response.status_code == 201, response.text
    body = response.json()

    assert re.fullmatch(r'[A-Za-z0-9]{16}', body['id'])
    assert set(body) == {
        'id',
        'version',
        'name',
        'price',
        'description',
        'createdAt',
        'updatedAt',
    }
    assert isinstance(body['price'], (int, float)) and not isinstance(
        body['price'], bool
    )
    assert Decimal(str(body['price'])) == Decimal(str(price))
    async with database_engine.connect() as observer:
        stored = (
            await observer.execute(
                select(ItemORM.price).where(ItemORM.id == body['id'])
            )
        ).scalar_one()

    assert isinstance(stored, Decimal) and stored == Decimal(str(price))
    read = await contract_client.get(f"/api/v1/items/{body['id']}")

    assert read.json() == body


@pytest.mark.parametrize('method', ['POST', 'PATCH', 'PUT'])
@pytest.mark.parametrize(
    'price',
    [
        0,
        -0.01,
        100000000,
        1.001,
        True,
        False,
        None,
        '1.230',
        ' 1.2',
        '1e2',
        'NaN',
        {'amount': 1},
    ],
)
async def test_rejected_prices_never_change_mysql(
    database_engine: AsyncEngine,
    contract_client: httpx.AsyncClient,
    method: str,
    price: object,
) -> None:
    seed = await contract_client.post(
        '/api/v1/items/',
        json={'name': 'Before', 'price': '12.34', 'description': 'Original'},
    )

    assert seed.status_code == 201
    identifier = seed.json()['id']

    async with database_engine.connect() as observer:
        before = (
            await observer.execute(
                select(ItemORM.id, ItemORM.name, ItemORM.price, ItemORM.description)
            )
        ).all()

    path = '/api/v1/items/' if method == 'POST' else f'/api/v1/items/{identifier}'
    response = await contract_client.request(
        method,
        path,
        json={
            'expected_version': 1,
            'name': 'After',
            'price': price,
            'description': 'Changed',
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()['status'] == 422
    async with database_engine.connect() as observer:
        after = (
            await observer.execute(
                select(ItemORM.id, ItemORM.name, ItemORM.price, ItemORM.description)
            )
        ).all()

    assert before == after


@pytest.mark.parametrize('token', ['NaN', 'Infinity', '-Infinity'])
async def test_nonfinite_json_prices_are_rejected(
    database_engine: AsyncEngine,
    contract_client: httpx.AsyncClient,
    token: str,
) -> None:
    response = await contract_client.post(
        '/api/v1/items/',
        content='{"name":"Invalid","price":' + token + '}',
        headers={'content-type': 'application/json'},
    )

    assert response.status_code == 422
    async with database_engine.connect() as observer:
        assert not list(await observer.scalars(select(ItemORM.id)))


@pytest.mark.parametrize('field', ['min_price', 'max_price'])
@pytest.mark.parametrize(
    'value', ['0', '1.234', ' 1.2', '+1', '1e2', '99999999.999', 'NaN']
)
async def test_price_filters_reject_the_same_invalid_decimal_spellings(
    contract_client: httpx.AsyncClient,
    field: str,
    value: str,
) -> None:
    response = await contract_client.get('/api/v1/items/', params={field: value})

    assert response.status_code == 422, response.text


async def test_fractional_price_filters_are_inclusive_and_share_decimal_validation(
    contract_client: httpx.AsyncClient,
) -> None:
    for price in ['0.01', '12.33', '12.34', '12.35', '99999999.99']:
        assert (
            await contract_client.post(
                '/api/v1/items/', json={'name': price, 'price': price}
            )
        ).status_code == 201

    response = await contract_client.get(
        '/api/v1/items/', params={'min_price': '12.34', 'max_price': '12.35'}
    )

    assert response.status_code == 200
    assert [item['price'] for item in response.json()['data']] == [12.34, 12.35]
    exact = await contract_client.get(
        '/api/v1/items/', params={'min_price': '12.34', 'max_price': '12.34'}
    )

    assert [item['price'] for item in exact.json()['data']] == [12.34]
    assert (
        await contract_client.get(
            '/api/v1/items/', params={'min_price': '12.35', 'max_price': '12.34'}
        )
    ).status_code == 422


async def test_existing_alphanumeric_id_and_invalid_stored_price_use_controller_boundary(
    database_engine: AsyncEngine,
    contract_client: httpx.AsyncClient,
) -> None:
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    async with factory() as seed, seed.begin():
        seed.add(ItemORM(id='A1b2C3d4E5f6G7h8', name='Before', price=Decimal('0.00')))

    failed = await contract_client.patch(
        '/api/v1/items/A1b2C3d4E5f6G7h8', json={'name': 'After', 'expected_version': 1}
    )

    assert (
        failed.status_code == 500
        and failed.json()['message'] == 'Internal Server Error'
    )
    async with database_engine.connect() as observer:
        row = (await observer.execute(select(ItemORM.name, ItemORM.price))).one()

    assert row == ('Before', Decimal('0.00'))
    repaired = await contract_client.patch(
        '/api/v1/items/A1b2C3d4E5f6G7h8', json={'price': '0.01', 'expected_version': 1}
    )

    assert repaired.status_code == 200 and repaired.json()['price'] == 0.01
    assert repaired.json()['id'] == 'A1b2C3d4E5f6G7h8'
