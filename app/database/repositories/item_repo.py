from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Result, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.entities.item_orm import ItemORM
from app.models.item_model import ItemBase, ItemPaginationQuery
from app.models.parameters_model import HexId


class ItemRepository:
    async def get_all(self, session: AsyncSession) -> Sequence[ItemORM]:
        result: Result[tuple[ItemORM]] = await session.execute(select(ItemORM))

        return result.scalars().all()

    async def find_and_count(
        self, session: AsyncSession, payload: ItemPaginationQuery
    ) -> tuple[Sequence[ItemORM], int]:
        filters: list[ColumnElement[bool]] = []

        if payload.search:
            pattern: str = f"%{payload.search.strip()}%"
            filters.append(
                or_(
                    ItemORM.name.ilike(pattern),
                    ItemORM.description.ilike(pattern),
                )
            )

        if payload.min_price is not None:
            filters.append(ItemORM.price >= payload.min_price)

        if payload.max_price is not None:
            filters.append(ItemORM.price <= payload.max_price)

        sort_column = getattr(ItemORM, payload.sort)
        sort_expr = sort_column.desc() if payload.order == "desc" else sort_column.asc()

        base_query: Select[tuple[ItemORM]] = (
            select(ItemORM).where(*filters).order_by(sort_expr)
        )

        count_query: Select[tuple[int]] = select(func.count()).select_from(
            base_query.subquery()
        )

        data_query: Select[tuple[ItemORM]] = base_query.offset(payload.offset).limit(
            payload.limit
        )

        total: int = await session.scalar(count_query) or 0
        data: Sequence[ItemORM] = (await session.execute(data_query)).scalars().all()

        return data, total

    async def get_by_id(self, session: AsyncSession, id: HexId) -> ItemORM | None:
        result: Result[tuple[ItemORM]] = await session.execute(
            select(ItemORM).where(ItemORM.id == id)
        )

        return result.scalar_one_or_none()

    async def create(self, session: AsyncSession, *, item_in: ItemBase) -> ItemORM:
        item: ItemORM = ItemORM(**item_in.model_dump())
        session.add(item)

        await session.commit()
        await session.refresh(item)

        return item

    async def update(
        self,
        session: AsyncSession,
        obj: ItemORM,
        new_data: dict[str, Any],
    ) -> ItemORM:
        for field, value in new_data.items():
            setattr(obj, field, value)

        await session.commit()
        await session.refresh(obj)

        return obj

    async def delete(
        self,
        session: AsyncSession,
        obj: ItemORM,
    ) -> ItemORM:
        await session.delete(obj)
        await session.commit()

        return obj


repo: ItemRepository = ItemRepository()
