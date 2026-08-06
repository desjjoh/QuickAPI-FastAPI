from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.database import Base
from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import (
    ItemListQuery,
    ItemRepository,
    ItemSort,
    SortOrder,
)

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def sessions(tmp_path: Path) -> AsyncIterator[SessionFactory]:
    """Give every test a private database and access to fresh sessions."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'items.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def seed(session: AsyncSession) -> list[ItemORM]:
    repository = ItemRepository()
    return [
        await repository.create(
            session,
            item_in={"name": "Alpha", "description": None, "price": 10},
        ),
        await repository.create(
            session,
            item_in={"name": "Bravo", "description": "alpha detail", "price": 20},
        ),
        await repository.create(
            session,
            item_in={"name": "Charlie", "description": "last", "price": 30},
        ),
    ]


@pytest.mark.asyncio
async def test_create_get_all_get_by_id_update_and_delete(
    sessions: SessionFactory,
) -> None:
    repository = ItemRepository()
    async with sessions() as session:
        item = await repository.create(
            session, item_in={"name": "Original", "description": None, "price": 2.5}
        )
        assert list(await repository.get_all(session)) == [item]
        assert await repository.get_by_id(session, item.id) is item
        assert await repository.get_by_id(session, "0" * 16) is None

        assert (
            await repository.update(
                session, item, {"name": "Updated", "description": "saved", "price": 3}
            )
            is item
        )
        assert (item.name, item.description, float(item.price)) == (
            "Updated",
            "saved",
            3.0,
        )
        assert await repository.delete(session, item) is item
        assert await repository.get_all(session) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected", "count"),
    [
        (
            ItemListQuery(limit=10, offset=0, search="alpha", sort=ItemSort.ITEM_NAME),
            ["Bravo", "Alpha"],
            2,
        ),
        (
            ItemListQuery(
                limit=10, offset=0, search="Charlie", sort=ItemSort.ITEM_NAME
            ),
            ["Charlie"],
            1,
        ),
        (
            ItemListQuery(
                limit=10, offset=0, search="missing", sort=ItemSort.ITEM_NAME
            ),
            [],
            0,
        ),
        (
            ItemListQuery(limit=10, offset=0, min_price=20, sort=ItemSort.ITEM_NAME),
            ["Charlie", "Bravo"],
            2,
        ),
        (
            ItemListQuery(limit=10, offset=0, max_price=20, sort=ItemSort.ITEM_NAME),
            ["Bravo", "Alpha"],
            2,
        ),
        (
            ItemListQuery(
                limit=10,
                offset=0,
                min_price=15,
                max_price=25,
                sort=ItemSort.ITEM_NAME,
            ),
            ["Bravo"],
            1,
        ),
        (
            ItemListQuery(limit=1, offset=1, sort=ItemSort.ITEM_NAME),
            ["Bravo"],
            3,
        ),
        (ItemListQuery(limit=0, offset=0, sort=ItemSort.ITEM_NAME), [], 3),
        (ItemListQuery(limit=10, offset=20, sort=ItemSort.ITEM_NAME), [], 3),
    ],
)
async def test_find_and_count_filters_and_pagination(
    sessions: SessionFactory,
    query: ItemListQuery,
    expected: list[str],
    count: int,
) -> None:
    async with sessions() as session:
        await seed(session)
        items, total = await ItemRepository().find_and_count(session, query)
        assert [item.name for item in items] == expected
        assert total == count


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", list(ItemSort))
@pytest.mark.parametrize("order", list(SortOrder))
async def test_find_and_count_supports_every_sort_direction(
    sessions: SessionFactory, sort: ItemSort, order: SortOrder
) -> None:
    async with sessions() as session:
        await seed(session)
        items, total = await ItemRepository().find_and_count(
            session, ItemListQuery(limit=10, offset=0, sort=sort, order=order)
        )
        values = [getattr(item, sort.value) for item in items]
        assert values == sorted(values, reverse=order is SortOrder.desc)
        assert total == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_commit_failure_rolls_back_propagates_and_session_is_reusable(
    sessions: SessionFactory, operation: str
) -> None:
    repository = ItemRepository()
    async with sessions() as session:
        existing = await repository.create(
            session, item_in={"name": "Before", "description": None, "price": 1}
        )
        real_commit, real_rollback = session.commit, session.rollback
        session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
        session.rollback = AsyncMock(wraps=real_rollback)

        with pytest.raises(RuntimeError, match="commit failed"):
            if operation == "create":
                await repository.create(
                    session, item_in={"name": "Partial", "price": 99}
                )
            elif operation == "update":
                await repository.update(session, existing, {"name": "Partial"})
            else:
                await repository.delete(session, existing)

        session.rollback.assert_awaited_once()
        session.commit = real_commit
        await repository.create(session, item_in={"name": "Reusable", "price": 2})

    async with sessions() as fresh:
        names = list(await fresh.scalars(select(ItemORM.name).order_by(ItemORM.name)))
        expected = ["Before", "Reusable"]
        assert names == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_refresh_failure_rolls_back_propagates_and_session_is_reusable(
    sessions: SessionFactory, operation: str
) -> None:
    repository = ItemRepository()
    async with sessions() as session:
        existing = await repository.create(
            session, item_in={"name": "Before", "description": None, "price": 1}
        )
        real_refresh, real_rollback = session.refresh, session.rollback
        session.refresh = AsyncMock(side_effect=RuntimeError("refresh failed"))
        session.rollback = AsyncMock(wraps=real_rollback)

        with pytest.raises(RuntimeError, match="refresh failed"):
            if operation == "create":
                await repository.create(
                    session, item_in={"name": "Partial", "price": 99}
                )
            else:
                await repository.update(session, existing, {"name": "Partial"})

        session.rollback.assert_awaited_once()
        session.refresh = real_refresh
        await repository.create(session, item_in={"name": "Reusable", "price": 2})

    async with sessions() as fresh:
        names = list(await fresh.scalars(select(ItemORM.name).order_by(ItemORM.name)))
        assert names == ["Before", "Reusable"]
