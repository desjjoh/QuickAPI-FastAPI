from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.entities.item_orm import ItemORM
from app.models.item_model import CreateItemRequest


class ItemRepository:
    async def get_all(self, session: AsyncSession) -> Sequence[ItemORM]:
        result = await session.execute(select(ItemORM))

        return result.scalars().all()

    async def get_by_id(self, session: AsyncSession, item_id: str) -> ItemORM | None:
        result = await session.execute(select(ItemORM).where(ItemORM.id == item_id))

        return result.scalar_one_or_none()

    async def create(
        self, session: AsyncSession, *, item_in: CreateItemRequest
    ) -> ItemORM:
        item = ItemORM(**item_in.model_dump())
        session.add(item)

        await session.commit()
        await session.refresh(item)

        return item


repo = ItemRepository()
