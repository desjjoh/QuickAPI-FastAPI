import httpx
import pytest

from .helpers import ITEMS_URL, assert_validation_error, create_item

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_list_defaults_and_empty_results(client: httpx.AsyncClient) -> None:
    empty = await client.get(ITEMS_URL)
    assert empty.status_code == 200
    assert empty.json() == {"data": [], "total": 0, "page": 1, "limit": 20}
    await create_item(client, "Default", 7)
    body = (await client.get(ITEMS_URL)).json()
    assert body["page"] == 1 and body["limit"] == 20 and body["total"] == 1


async def test_list_multiple_final_and_out_of_range_pages(
    client: httpx.AsyncClient,
) -> None:
    for index in range(5):
        await create_item(client, f"Item {index}", float(index))
    first = (await client.get(ITEMS_URL, params={"page": 1, "limit": 2})).json()
    second = (await client.get(ITEMS_URL, params={"page": 2, "limit": 2})).json()
    final = (await client.get(ITEMS_URL, params={"page": 3, "limit": 2})).json()
    beyond = (await client.get(ITEMS_URL, params={"page": 4, "limit": 2})).json()
    assert [len(page["data"]) for page in (first, second, final, beyond)] == [
        2,
        2,
        1,
        0,
    ]
    assert all(page["total"] == 5 for page in (first, second, final, beyond))
    ids = {item["id"] for page in (first, second, final) for item in page["data"]}
    assert len(ids) == 5


@pytest.mark.parametrize("limit", [1, 100])
async def test_list_accepts_boundary_limits(
    client: httpx.AsyncClient, limit: int
) -> None:
    await create_item(client)
    response = await client.get(ITEMS_URL, params={"limit": limit})
    assert response.status_code == 200
    assert response.json()["limit"] == limit


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"page": "one"},
        {"limit": 0},
        {"limit": 101},
        {"limit": "many"},
    ],
)
async def test_list_rejects_invalid_page_and_limit(
    client: httpx.AsyncClient, params: dict[str, str | int]
) -> None:
    assert_validation_error(await client.get(ITEMS_URL, params=params))


@pytest.mark.parametrize("sort", ["name", "price", "created_at"])
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_list_supports_every_sort_and_order(
    client: httpx.AsyncClient, sort: str, order: str
) -> None:
    created = [
        await create_item(client, "Bravo", 20),
        await create_item(client, "Alpha", 30),
        await create_item(client, "Charlie", 10),
    ]
    response = await client.get(ITEMS_URL, params={"sort": sort, "order": order})
    assert response.status_code == 200
    actual = response.json()["data"]
    reverse = order == "desc"
    if sort == "created_at":
        expected = sorted(
            created, key=lambda item: (item[sort], item["id"]), reverse=reverse
        )
        assert [item[sort] for item in actual] == [item[sort] for item in expected]
    else:
        assert [item[sort] for item in actual] == sorted(
            [item[sort] for item in created], reverse=reverse
        )


async def test_list_order_is_stable_when_sort_values_are_equal(
    client: httpx.AsyncClient,
) -> None:
    for name in ("One", "Two", "Three"):
        await create_item(client, name, 5)
    params = {"sort": "price", "order": "asc"}
    first = [
        item["id"]
        for item in (await client.get(ITEMS_URL, params=params)).json()["data"]
    ]
    second = [
        item["id"]
        for item in (await client.get(ITEMS_URL, params=params)).json()["data"]
    ]
    assert first == second


@pytest.mark.parametrize("search", ["aLpHa", "NEEDLE"])
async def test_list_searches_name_and_description_case_insensitively(
    client: httpx.AsyncClient, search: str
) -> None:
    await create_item(client, "Alpha blade", 1, "ordinary")
    await create_item(client, "Other", 2, "A needle in this description")
    body = (await client.get(ITEMS_URL, params={"search": search})).json()
    assert body["total"] == 1


async def test_list_whitespace_only_search_does_not_filter(
    client: httpx.AsyncClient,
) -> None:
    await create_item(client, "One", 1, None)
    await create_item(client, "Two", 2, "text")
    assert (await client.get(ITEMS_URL, params={"search": "   "})).json()["total"] == 2


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"min_price": 10}, [10, 15, 20]),
        ({"max_price": 15}, [5, 10, 15]),
        ({"min_price": 10, "max_price": 15}, [10, 15]),
        ({"min_price": 15, "max_price": 15}, [15]),
    ],
)
async def test_list_price_filters_are_inclusive(
    client: httpx.AsyncClient, params: dict[str, int], expected: list[int]
) -> None:
    for price in (5, 10, 15, 20):
        await create_item(client, f"Price {price}", price)
    query: dict[str, str | int] = {**params, "sort": "price", "order": "asc"}
    body = (await client.get(ITEMS_URL, params=query)).json()
    assert [item["price"] for item in body["data"]] == expected


async def test_list_rejects_inverted_price_range(client: httpx.AsyncClient) -> None:
    assert_validation_error(
        await client.get(ITEMS_URL, params={"min_price": 20, "max_price": 10})
    )
