import httpx
import pytest

from .helpers import ITEMS_URL, MISSING_ID, assert_validation_error, create_item

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_delete_existing_item_and_persisted_absence(
    client: httpx.AsyncClient,
) -> None:
    item = await create_item(client, "Disposable", 1)
    deleted = await client.post(
        f"{ITEMS_URL}{item['id']}" + '/delete', json={'expected_version': 1}
    )

    assert deleted.status_code == 200
    assert deleted.json() == item
    assert (await client.get(f"{ITEMS_URL}{item['id']}")).status_code == 404
    listing = (await client.get(ITEMS_URL)).json()

    assert listing["total"] == 0 and listing["data"] == []


@pytest.mark.parametrize("item_id", ["bad", "_" * 16, "0" * 15])
async def test_delete_rejects_syntactically_invalid_ids(
    client: httpx.AsyncClient, item_id: str
) -> None:
    assert_validation_error(
        await client.post(
            f"{ITEMS_URL}{item_id}" + '/delete', json={'expected_version': 1}
        )
    )


async def test_delete_valid_missing_id(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"{ITEMS_URL}{MISSING_ID}" + '/delete', json={'expected_version': 1}
    )

    assert response.status_code == 404


async def test_repeated_delete_returns_not_found(client: httpx.AsyncClient) -> None:
    item = await create_item(client)

    assert (
        await client.post(
            f"{ITEMS_URL}{item['id']}" + '/delete', json={'expected_version': 1}
        )
    ).status_code == 200
    repeated = await client.post(
        f"{ITEMS_URL}{item['id']}" + '/delete', json={'expected_version': 1}
    )

    assert repeated.status_code == 404
