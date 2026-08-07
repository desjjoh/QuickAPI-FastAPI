import httpx
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_item_crud_patch_omission_and_not_found(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/items/", json={"name": "Sword", "price": 12.5, "description": "steel"}
    )
    assert created.status_code == 201
    item = created.json()
    fetched = await client.get(f"/api/v1/items/{item['id']}")
    assert fetched.json()["name"] == "Sword"
    patched = await client.patch(f"/api/v1/items/{item['id']}", json={"price": 15})
    assert patched.status_code == 200
    assert (
        patched.json()["name"] == "Sword" and patched.json()["description"] == "steel"
    )
    replaced = await client.put(
        f"/api/v1/items/{item['id']}",
        json={"name": "Shield", "price": 20, "description": None},
    )
    assert replaced.status_code == 200 and replaced.json()["name"] == "Shield"
    deleted = await client.delete(f"/api/v1/items/{item['id']}")
    assert deleted.status_code == 200
    missing = await client.get(f"/api/v1/items/{item['id']}")
    assert missing.status_code == 404
    assert missing.json()["status"] == 404


@pytest.mark.asyncio
async def test_pagination_filtering_and_sorting(
    client: httpx.AsyncClient,
) -> None:
    for name, price in [("Gamma", 30), ("Alpha sword", 10), ("Beta sword", 20)]:
        assert (
            await client.post("/api/v1/items/", json={"name": name, "price": price})
        ).status_code == 201
    response = await client.get(
        "/api/v1/items/",
        params={
            "search": "sword",
            "min_price": 10,
            "max_price": 25,
            "sort": "price",
            "order": "desc",
            "page": 1,
            "limit": 1,
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 2 and body["limit"] == 1
    assert [item["name"] for item in body["data"]] == ["Beta sword"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("post", "/api/v1/items/", {"name": "", "price": -1}),
        ("patch", "/api/v1/items/0000000000000000", {}),
        ("patch", "/api/v1/items/0000000000000000", {"name": None}),
    ],
)
async def test_validation_envelope(
    client: httpx.AsyncClient, method: str, path: str, payload: dict[str, object]
) -> None:
    response = await getattr(client, method)(path, json=payload)
    assert response.status_code == 422
    assert response.json()["status"] == 422
    assert response.json()["message"].startswith("Validation failed:")
    assert isinstance(response.json()["timestamp"], int)
