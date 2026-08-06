from datetime import datetime

import httpx
import pytest

from .helpers import ITEMS_URL, assert_validation_error

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "Name only"},
        {"price": 1},
        {"name": "", "price": 1},
        {"name": "n" * 121, "price": 1},
        {"name": "negative", "price": -0.01},
        {"name": "verbose", "price": 1, "description": "d" * 501},
        {"name": None, "price": 1},
        {"name": "null price", "price": None},
        {"name": ["wrong"], "price": 1},
        {"name": "wrong price", "price": {"amount": 1}},
        {"name": "wrong description", "price": 1, "description": ["wrong"]},
    ],
)
async def test_create_rejects_invalid_payloads(
    client: httpx.AsyncClient, payload: dict[str, object]
) -> None:
    assert_validation_error(await client.post(ITEMS_URL, json=payload))


@pytest.mark.parametrize("price", [0, 0.01, 12.345])
async def test_create_accepts_zero_and_fractional_prices(
    client: httpx.AsyncClient, price: float
) -> None:
    response = await client.post(ITEMS_URL, json={"name": "Priced", "price": price})
    assert response.status_code == 201
    assert response.json()["price"] == pytest.approx(round(price, 2))


async def test_create_accepts_optional_and_null_description(
    client: httpx.AsyncClient,
) -> None:
    omitted = await client.post(ITEMS_URL, json={"name": "Omitted", "price": 2})
    explicit = await client.post(
        ITEMS_URL, json={"name": "Explicit", "price": 3, "description": None}
    )
    described = await client.post(
        ITEMS_URL, json={"name": "Described", "price": 4, "description": "details"}
    )
    assert omitted.json()["description"] is None
    assert explicit.json()["description"] is None
    assert described.json()["description"] == "details"


async def test_create_ignores_extra_fields(client: httpx.AsyncClient) -> None:
    response = await client.post(
        ITEMS_URL, json={"name": "Minimal", "price": 5, "unexpected": "ignored"}
    )
    assert response.status_code == 201
    assert "unexpected" not in response.json()


async def test_create_returns_and_persists_complete_resource(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        ITEMS_URL,
        json={"name": "Persistent", "price": 9.99, "description": "stored"},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "name",
        "price",
        "description",
        "created_at",
        "updated_at",
    }
    assert len(body["id"]) == 16
    int(body["id"], 16)
    datetime.fromisoformat(body["created_at"])
    datetime.fromisoformat(body["updated_at"])
    persisted = await client.get(f"{ITEMS_URL}{body['id']}")
    assert persisted.status_code == 200
    assert persisted.json() == body
