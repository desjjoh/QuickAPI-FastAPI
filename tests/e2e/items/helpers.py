from typing import Any

import httpx

ITEMS_URL = "/api/v1/items/"
MISSING_ID = "ffffffffffffffff"


async def create_item(
    client: httpx.AsyncClient,
    name: str = "Test item",
    price: float = 10.0,
    description: str | None = "Test description",
) -> dict[str, Any]:
    response = await client.post(
        ITEMS_URL,
        json={"name": name, "price": price, "description": description},
    )
    assert response.status_code == 201, response.text
    return response.json()


def assert_validation_error(response: httpx.Response) -> None:
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422
    assert body["message"].startswith("Validation failed:")
