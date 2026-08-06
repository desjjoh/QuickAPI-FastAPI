import httpx
import pytest

from .helpers import ITEMS_URL, MISSING_ID, assert_validation_error, create_item

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.mark.parametrize(
    ("replacement", "description"),
    [
        ({"name": "Replacement", "price": 42, "description": "new"}, "new"),
        ({"name": "Replacement", "price": 42}, None),
        ({"name": "Replacement", "price": 42, "description": None}, None),
    ],
)
async def test_put_replaces_every_field_and_optional_description(
    client: httpx.AsyncClient,
    replacement: dict[str, object],
    description: str | None,
) -> None:
    item = await create_item(client, "Old", 1, "old")
    response = await client.put(f"{ITEMS_URL}{item['id']}", json=replacement)
    assert response.status_code == 200
    assert response.json()["name"] == "Replacement"
    assert response.json()["price"] == 42
    assert response.json()["description"] == description


@pytest.mark.parametrize(
    "replacement",
    [
        {},
        {"name": "Missing price"},
        {"price": 1},
        {"name": None, "price": 1},
        {"name": "", "price": 1},
        {"name": "x" * 121, "price": 1},
        {"name": "Negative", "price": -1},
        {"name": "Verbose", "price": 1, "description": "x" * 501},
    ],
)
async def test_put_validation_failures_are_independent(
    client: httpx.AsyncClient, replacement: dict[str, object]
) -> None:
    item = await create_item(client)
    assert_validation_error(
        await client.put(f"{ITEMS_URL}{item['id']}", json=replacement)
    )


async def test_put_missing_resource(client: httpx.AsyncClient) -> None:
    response = await client.put(
        f"{ITEMS_URL}{MISSING_ID}", json={"name": "Missing", "price": 1}
    )
    assert response.status_code == 404


async def test_put_persists_to_subsequent_get(client: httpx.AsyncClient) -> None:
    item = await create_item(client)
    replaced = await client.put(
        f"{ITEMS_URL}{item['id']}",
        json={"name": "Persisted", "price": 99, "description": "replacement"},
    )
    fetched = await client.get(f"{ITEMS_URL}{item['id']}")
    assert replaced.status_code == fetched.status_code == 200
    assert fetched.json() == replaced.json()
