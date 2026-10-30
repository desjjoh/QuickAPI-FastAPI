from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import NotRequired, TypedDict

from fastapi import HTTPException
from sqlalchemy import (
    ColumnElement,
    CursorResult,
    Result,
    Select,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models.parameters_model import EntityId
from app.common.models.version_model import MAX_VERSION
from app.database.entities.item_orm import ItemORM


class ItemCreateData(TypedDict):
    name: str
    description: NotRequired[str | None]
    price: Decimal


class ItemUpdateData(TypedDict, total=False):
    name: str
    description: str | None
    price: Decimal


class ItemSort(StrEnum):
    CREATED_AT = "createdAt"
    ITEM_NAME = "name"
    PRICE = "price"


class SortOrder(StrEnum):
    asc = "asc"
    desc = "desc"


@dataclass(frozen=True, slots=True)
class ItemListQuery:
    limit: int
    offset: int
    search: str | None = None
    sort: ItemSort = ItemSort.CREATED_AT
    order: SortOrder = SortOrder.desc
    min_price: Decimal | None = None
    max_price: Decimal | None = None


class ItemRepository:
    """Persist items within caller-owned transactions; never commit or roll back."""

    @staticmethod
    def require_transaction(session: AsyncSession) -> None:
        if not session.in_transaction():
            raise RuntimeError('Item mutations require a caller-owned transaction.')

    async def create(
        self, session: AsyncSession, *, item_in: ItemCreateData
    ) -> ItemORM:
        self.require_transaction(session)
        item: ItemORM = ItemORM(**item_in)

        session.add(item)

        await session.flush()
        await session.refresh(item)

        return item

    async def get_all(self, session: AsyncSession) -> Sequence[ItemORM]:
        result: Result[tuple[ItemORM]] = await session.execute(select(ItemORM))

        return result.scalars().all()

    async def find_and_count(
        self, session: AsyncSession, payload: ItemListQuery
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

        sort_column = {
            ItemSort.CREATED_AT: ItemORM.created_at,
            ItemSort.ITEM_NAME: ItemORM.name,
            ItemSort.PRICE: ItemORM.price,
        }[payload.sort]
        sort_expr = sort_column.desc() if payload.order == "desc" else sort_column.asc()

        base_query: Select[tuple[ItemORM]] = (
            select(ItemORM)
            .where(*filters)
            .order_by(
                sort_expr,
                ItemORM.id.desc() if payload.order == 'desc' else ItemORM.id.asc(),
            )
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

    async def get_by_id(self, session: AsyncSession, id: EntityId) -> ItemORM | None:
        result: Result[tuple[ItemORM]] = await session.execute(
            select(ItemORM).where(ItemORM.id == id)
        )

        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self, session: AsyncSession, id: EntityId
    ) -> ItemORM | None:
        self.require_transaction(session)
        result = await session.execute(
            select(ItemORM)
            .where(ItemORM.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        return result.scalar_one_or_none()

    async def update(
        self,
        session: AsyncSession,
        obj: ItemORM,
        new_data: ItemUpdateData,
        expected_version: int,
    ) -> ItemORM:
        self.require_transaction(session)
        result = await session.execute(
            update(ItemORM)
            .where(
                ItemORM.id == obj.id,
                ItemORM.version == expected_version,
                ItemORM.version < MAX_VERSION,
            )
            .values(**new_data, version=ItemORM.version + 1)
            .execution_options(synchronize_session=False)
        )

        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise HTTPException(
                409, 'Item version conflict; reload the item before retrying.'
            )

        await session.flush()
        await session.refresh(obj)

        return obj

    async def delete(
        self, session: AsyncSession, obj: ItemORM, expected_version: int
    ) -> ItemORM:
        self.require_transaction(session)
        result = await session.execute(
            delete(ItemORM)
            .where(ItemORM.id == obj.id, ItemORM.version == expected_version)
            .execution_options(synchronize_session=False)
        )

        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise HTTPException(
                409, 'Item version conflict; reload the item before retrying.'
            )

        session.expunge(obj)
        await session.flush()

        return obj


repo: ItemRepository = ItemRepository()
