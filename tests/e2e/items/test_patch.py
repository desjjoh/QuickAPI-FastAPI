import httpx
import pytest

from .helpers import ITEMS_URL, MISSING_ID, assert_validation_error, create_item

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        (
            {"name": "Renamed"},
            {"name": "Renamed", "price": 10, "description": "original"},
        ),
        (
            {"price": 22.5},
            {"name": "Original", "price": 22.5, "description": "original"},
        ),
        (
            {"description": "changed"},
            {"name": "Original", "price": 10, "description": "changed"},
        ),
        ({"description": None}, {"name": "Original", "price": 10, "description": None}),
        (
            {"name": "Both", "price": 30},
            {"name": "Both", "price": 30, "description": "original"},
        ),
    ],
)
async def test_patch_fields_independently_and_preserves_omissions(
    client: httpx.AsyncClient,
    patch: dict[str, object],
    expected: dict[str, object],
) -> None:
    item = await create_item(client, "Original", 10, "original")
    response = await client.patch(f"{ITEMS_URL}{item['id']}", json=patch)
    assert response.status_code == 200
    assert all(response.json()[key] == value for key, value in expected.items())


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"name": None},
        {"price": None},
        {"name": ""},
        {"name": "x" * 121},
        {"price": -1},
        {"description": "x" * 501},
        {"price": "not-a-price"},
    ],
)
async def test_patch_rejects_empty_null_and_invalid_values(
    client: httpx.AsyncClient, patch: dict[str, object]
) -> None:
    item = await create_item(client)
    assert_validation_error(await client.patch(f"{ITEMS_URL}{item['id']}", json=patch))


async def test_patch_missing_resource(client: httpx.AsyncClient) -> None:
    response = await client.patch(f"{ITEMS_URL}{MISSING_ID}", json={"name": "Nope"})
    assert response.status_code == 404


async def test_patch_persists_to_subsequent_get(client: httpx.AsyncClient) -> None:
    item = await create_item(client, "Before", 1, "before")
    patched = await client.patch(
        f"{ITEMS_URL}{item['id']}",
        json={"name": "After", "price": 2, "description": "after"},
    )
    fetched = await client.get(f"{ITEMS_URL}{item['id']}")
    assert patched.status_code == fetched.status_code == 200
    assert fetched.json() == patched.json()
