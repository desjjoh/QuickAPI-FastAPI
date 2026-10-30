"""Item operations within the caller's session; HTTP models belong to controllers."""

from collections.abc import Sequence

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.items.models.item_model import ItemBase
from app.api.v1.items.models.item_replace_model import ReplaceItemRequest
from app.api.v1.items.models.item_update_model import UpdateItemRequest
from app.api.v1.items.models.pagination_query_model import ItemPaginationQuery
from app.common.models.converter import model_to
from app.common.models.parameters_model import EntityId
from app.common.models.version_model import VersionInput
from app.config.database import get_session
from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import (
    ItemCreateData,
    ItemListQuery,
    ItemUpdateData,
    repo,
)


class ItemService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payload: ItemBase) -> ItemORM:
        item = await repo.create(self.db, item_in=model_to(ItemCreateData, payload))

        return item

    async def get_all(
        self, query: ItemPaginationQuery
    ) -> tuple[Sequence[ItemORM], int]:
        items, count = await repo.find_and_count(
            self.db, model_to(ItemListQuery, query)
        )

        return items, count

    async def get(self, id: EntityId) -> ItemORM:
        item = await repo.get_by_id(self.db, id)

        if item is None:
            raise HTTPException(404, "No item exists with the provided identifier.")

        return item

    async def update(self, id: EntityId, payload: UpdateItemRequest) -> ItemORM:
        item = await self._mutation_item(id, payload.expected_version)

        updated = await repo.update(
            self.db,
            item,
            model_to(
                ItemUpdateData,
                payload,
                exclude_unset=True,
                exclude={"expected_version"},
            ),
            payload.expected_version,
        )

        return updated

    async def replace(self, id: EntityId, payload: ReplaceItemRequest) -> ItemORM:
        item = await self._mutation_item(id, payload.expected_version)

        updated = await repo.update(
            self.db,
            item,
            model_to(
                ItemUpdateData,
                payload,
                exclude_unset=False,
                exclude={"expected_version"},
            ),
            payload.expected_version,
        )

        return updated

    async def delete(self, id: EntityId, payload: VersionInput) -> ItemORM:
        item = await self._mutation_item(id, payload.expected_version)

        removed = await repo.delete(self.db, item, payload.expected_version)

        return removed

    async def _mutation_item(self, id: EntityId, expected_version: int) -> ItemORM:
        item = await repo.get_by_id_for_update(self.db, id)

        if item is None:
            raise HTTPException(404, 'No item exists with the provided identifier.')

        if item.version != expected_version:
            raise HTTPException(
                409, 'Item version conflict; reload the item before retrying.'
            )

        return item


def get_item_service(db: AsyncSession = Depends(get_session)) -> ItemService:
    return ItemService(db)
