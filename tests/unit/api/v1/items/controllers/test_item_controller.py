import os
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("APP_NAME", "QuickAPI Tests")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "5000")
os.environ.setdefault(
    "DATABASE_URL", "mysql+asyncmy://quickapi:test@localhost:3306/quickapi_test"
)

from app.api.v1.items.controllers import item_controller
from app.api.v1.items.models.item_model import ItemBase, ItemResponse
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.api.v1.items.models.pagination_query_model import ItemPaginationQuery
from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import ItemUpdateData

pytestmark = pytest.mark.unit


class ItemControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        self.item = cast(
            ItemORM,
            SimpleNamespace(
                id="0123456789abcdef",
                name="Iron Sword",
                price=49.99,
                description="A finely crafted steel blade.",
                created_at=timestamp,
                updated_at=timestamp,
            ),
        )

    async def _update(
        self, payload: UpdateItemRequest
    ) -> tuple[ItemResponse, AsyncMock]:
        async def apply_update(
            db: AsyncSession, obj: ItemORM, new_data: ItemUpdateData
        ) -> ItemORM:
            for field, value in new_data.items():
                setattr(obj, field, value)
            return obj

        with (
            patch.object(
                item_controller.repo,
                "get_by_id",
                new=AsyncMock(return_value=self.item),
            ),
            patch.object(
                item_controller.repo,
                "update",
                new=AsyncMock(side_effect=apply_update),
            ) as update,
        ):
            response = await item_controller.update(self.item.id, payload, AsyncMock())

        return response, update

    async def test_patch_changes_only_explicitly_supplied_field(self) -> None:
        payload = UpdateItemRequest.model_validate({"price": 59.99})
        response, update = await self._update(payload)

        update.assert_awaited_once()
        self.assertEqual(update.await_args_list[0].args[2], {"price": 59.99})
        self.assertEqual(response.price, 59.99)
        self.assertEqual(response.name, "Iron Sword")
        self.assertEqual(response.description, "A finely crafted steel blade.")

    async def test_patch_explicit_null_clears_nullable_description(self) -> None:
        payload = UpdateItemRequest.model_validate({"description": None})
        response, update = await self._update(payload)

        update.assert_awaited_once()
        self.assertEqual(update.await_args_list[0].args[2], {"description": None})
        self.assertIsNone(response.description)
        self.assertEqual(response.name, "Iron Sword")
        self.assertEqual(response.price, 49.99)

    async def test_create_converts_payload_and_returns_created_item(self) -> None:
        payload = ItemBase(name="Iron Sword", price=49.99, description=None)
        with patch.object(
            item_controller.repo, "create", new=AsyncMock(return_value=self.item)
        ) as create:
            response = await item_controller.create(payload, AsyncMock())

        self.assertEqual(response.id, self.item.id)
        self.assertEqual(create.await_args.kwargs["item_in"], payload.model_dump())

    async def test_list_converts_query_and_returns_page(self) -> None:
        query = ItemPaginationQuery()
        with patch.object(
            item_controller.repo,
            "find_and_count",
            new=AsyncMock(return_value=([self.item], 1)),
        ) as find_and_count:
            response = await item_controller.get_all(query, AsyncMock())

        self.assertEqual(response.total, 1)
        self.assertEqual(response.page, query.page)
        self.assertEqual(response.limit, query.limit)
        self.assertEqual(response.data[0].id, self.item.id)
        find_and_count.assert_awaited_once()

    async def test_get_returns_item_and_reports_missing_item(self) -> None:
        with patch.object(
            item_controller.repo,
            "get_by_id",
            new=AsyncMock(side_effect=[self.item, None]),
        ):
            response = await item_controller.get(self.item.id, AsyncMock())
            self.assertEqual(response.id, self.item.id)

            with self.assertRaises(item_controller.HTTPException) as error:
                await item_controller.get("ffffffffffffffff", AsyncMock())

        self.assertEqual(error.exception.status_code, 404)

    async def test_patch_reports_missing_item(self) -> None:
        with (
            patch.object(
                item_controller.repo, "get_by_id", new=AsyncMock(return_value=None)
            ),
            self.assertRaises(item_controller.HTTPException) as error,
        ):
            await item_controller.update(
                "ffffffffffffffff", UpdateItemRequest(price=1), AsyncMock()
            )

        self.assertEqual(error.exception.status_code, 404)

    async def test_replace_updates_all_fields_and_reports_missing_item(self) -> None:
        payload = ItemBase(name="Replacement", price=10, description=None)
        update = AsyncMock(return_value=self.item)
        with (
            patch.object(
                item_controller.repo,
                "get_by_id",
                new=AsyncMock(side_effect=[self.item, None]),
            ),
            patch.object(item_controller.repo, "update", new=update),
        ):
            response = await item_controller.replace(self.item.id, payload, AsyncMock())
            self.assertEqual(response.id, self.item.id)
            self.assertEqual(update.await_args.args[2], payload.model_dump())

            with self.assertRaises(item_controller.HTTPException) as error:
                await item_controller.replace("ffffffffffffffff", payload, AsyncMock())

        self.assertEqual(error.exception.status_code, 404)

    async def test_delete_returns_removed_item_and_reports_missing_item(self) -> None:
        delete = AsyncMock(return_value=self.item)
        with (
            patch.object(
                item_controller.repo,
                "get_by_id",
                new=AsyncMock(side_effect=[self.item, None]),
            ),
            patch.object(item_controller.repo, "delete", new=delete),
        ):
            response = await item_controller.delete(self.item.id, AsyncMock())
            self.assertEqual(response.id, self.item.id)
            delete.assert_awaited_once()

            with self.assertRaises(item_controller.HTTPException) as error:
                await item_controller.delete("ffffffffffffffff", AsyncMock())

        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
