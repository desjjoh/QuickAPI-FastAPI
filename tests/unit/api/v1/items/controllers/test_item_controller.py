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
from app.api.v1.items.models.item_model import ItemResponse
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import ItemUpdateData

pytestmark = pytest.mark.unit


class UpdateItemControllerTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
