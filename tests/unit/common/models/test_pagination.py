import pytest
from pydantic import ValidationError

from app.common.models.pagination import PaginatedResult, PaginationQuery

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("page", "limit", "offset"), [(1, 20, 0), (2, 20, 20), (4, 5, 15)]
)
def test_offset(page: int, limit: int, offset: int) -> None:
    assert PaginationQuery(page=page, limit=limit).offset == offset


@pytest.mark.parametrize(
    "values", [{"page": 0}, {"limit": 0}, {"limit": 101}, {"order": "sideways"}]
)
def test_query_validation_boundaries(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PaginationQuery.model_validate(values)


@pytest.mark.parametrize(
    ("total", "limit", "pages"), [(0, 20, 1), (40, 20, 2), (41, 20, 3), (1, 0, 1)]
)
def test_total_pages(total: int, limit: int, pages: int) -> None:
    assert (
        PaginatedResult[int](data=[], total=total, page=1, limit=limit).total_pages
        == pages
    )


def test_models_are_frozen() -> None:
    query = PaginationQuery()
    result = PaginatedResult[int](data=[], total=0, page=1, limit=20)

    with pytest.raises(ValidationError):
        query.__setattr__("page", 2)

    with pytest.raises(ValidationError):
        result.__setattr__("total", 1)


@pytest.mark.parametrize('order', ['ASC', 'aSc', 'DESC', 'dEsC'])
def test_order_is_case_insensitive(order: str) -> None:
    query = PaginationQuery.model_validate({'order': order})

    assert query.order == order.lower()


def test_defaults_and_safe_integer_boundaries() -> None:
    maximum = 9007199254740991

    assert PaginationQuery().limit == 25
    assert PaginationQuery(page=maximum, limit=1).offset == maximum - 1
    assert PaginationQuery(page=maximum // 2 + 1, limit=2).offset == maximum - 1
    for values in ({'page': maximum + 1}, {'page': maximum, 'limit': 2}):
        with pytest.raises(ValidationError):
            PaginationQuery.model_validate(values)
