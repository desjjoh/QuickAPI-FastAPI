from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.api.v1.items.controllers import item_controller
from app.api.v1.items.models.item_model import ItemBase
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.api.v1.items.models.pagination_query_model import ItemPaginationQuery
from app.api.v1.items.services.item_service import ItemService

pytestmark = pytest.mark.unit


def item_data(price: float = 1) -> dict[str, object]:
    return {
        'id': '0123456789abcdef',
        'name': 'Item',
        'price': price,
        'description': None,
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC),
    }


@pytest.mark.parametrize(
    'operation', ['create', 'get_all', 'get', 'update', 'replace', 'delete']
)
async def test_controller_validates_service_results(operation: str) -> None:
    service = Mock(spec=ItemService)
    invalid = item_data(-1)
    result = ([invalid], 1) if operation == 'get_all' else invalid
    method = AsyncMock(return_value=result)

    setattr(service, operation, method)
    args: tuple[object, ...]

    if operation == 'create':
        args = (ItemBase(name='Item', price=Decimal('1'), description=None),)
    elif operation == 'get_all':
        args = (ItemPaginationQuery(),)
    elif operation in {'update', 'replace'}:
        payload = (
            UpdateItemRequest.model_validate({'price': 1})
            if operation == 'update'
            else ItemBase(name='Item', price=Decimal('1'), description=None)
        )
        args = ('0123456789abcdef', payload)
    else:
        args = ('0123456789abcdef',)

    controller = cast(
        Callable[..., Awaitable[object]], getattr(item_controller, operation)
    )

    with pytest.raises(ValidationError) as error:
        await controller(*args, service=service)

    assert any(detail['loc'] == ('price',) for detail in error.value.errors())
    method.assert_awaited_once()


async def test_list_builds_validated_items_and_preserves_pagination_metadata() -> None:
    service = cast(ItemService, Mock(spec=ItemService))
    method = AsyncMock(return_value=([item_data()], 7))
    service.get_all = method
    query = ItemPaginationQuery(page=2, limit=3)
    response = await item_controller.get_all(query, service)

    assert (response.page, response.limit, response.total) == (2, 3, 7)
    assert response.data[0].price == 1 and response.data[0].id == '0123456789abcdef'
    method.assert_awaited_once_with(query)
