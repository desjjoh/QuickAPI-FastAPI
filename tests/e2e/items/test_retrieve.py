import httpx
import pytest

from .helpers import ITEMS_URL, MISSING_ID, assert_validation_error, create_item

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_retrieve_existing_item(client: httpx.AsyncClient) -> None:
    item = await create_item(client, "Found", 12, "retrievable")
    response = await client.get(f"{ITEMS_URL}{item['id']}")
    assert response.status_code == 200
    assert response.json() == item


@pytest.mark.parametrize("item_id", ["short", "g" * 16, "A" * 16, "0" * 17])
async def test_retrieve_rejects_syntactically_invalid_ids(
    client: httpx.AsyncClient, item_id: str
) -> None:
    assert_validation_error(await client.get(f"{ITEMS_URL}{item_id}"))


async def test_retrieve_valid_missing_id(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{ITEMS_URL}{MISSING_ID}")
    assert response.status_code == 404
    assert response.json()["status"] == 404
