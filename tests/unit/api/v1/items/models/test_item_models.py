import pytest
from pydantic import ValidationError

from app.api.v1.items.models.item_model import ItemBase
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.api.v1.items.models.pagination_query_model import ItemPaginationQuery

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "a", "price": 0},
        {"name": "a" * 120, "price": 1.25, "description": None},
        {"name": "item", "price": 3, "description": "x" * 500},
    ],
)
def test_item_base_accepts_boundaries(payload: dict[str, object]) -> None:
    assert ItemBase.model_validate(payload).name == payload["name"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "ok"},
        {"price": 1},
        {"name": "", "price": 1},
        {"name": "x" * 121, "price": 1},
        {"name": "ok", "price": -0.01},
        {"name": "ok", "price": 1, "description": "x" * 501},
    ],
)
def test_item_base_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ItemBase.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "renamed"},
        {"price": 0},
        {"description": None},
        {"name": "renamed", "price": 2, "description": "new"},
    ],
)
def test_update_accepts_each_field_and_explicit_null_description(
    payload: dict[str, object],
) -> None:
    assert (
        UpdateItemRequest.model_validate(payload).model_dump(exclude_unset=True)
        == payload
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"price": None},
        {"name": ""},
        {"price": -1},
        {"description": "x" * 501},
    ],
)
def test_update_rejects_empty_null_or_invalid_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        UpdateItemRequest.model_validate(payload)


def test_update_distinguishes_omitted_fields() -> None:
    update = UpdateItemRequest.model_validate({"description": None})
    assert update.model_fields_set == {"description"}
    assert update.model_dump(exclude_unset=True) == {"description": None}


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"page": 1, "limit": 100, "sort": "name", "order": "desc"},
        {"min_price": 0},
        {"max_price": 0},
        {"min_price": 1, "max_price": 1},
    ],
)
def test_item_pagination_accepts_valid_matrix(values: dict[str, object]) -> None:
    ItemPaginationQuery.model_validate(values)


@pytest.mark.parametrize(
    "values",
    [
        {"page": 0},
        {"limit": 0},
        {"limit": 101},
        {"sort": "id"},
        {"order": "up"},
        {"min_price": -1},
        {"max_price": -1},
        {"min_price": 2, "max_price": 1},
    ],
)
def test_item_pagination_rejects_invalid_matrix(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ItemPaginationQuery.model_validate(values)
