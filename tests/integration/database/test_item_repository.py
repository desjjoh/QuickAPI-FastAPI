from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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
async def sessions(database_engine: AsyncEngine) -> AsyncIterator[SessionFactory]:
    """Give every test a private database and access to fresh sessions."""
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    yield factory


async def seed(session: AsyncSession) -> list[ItemORM]:
    repository = ItemRepository()

    return [
        await repository.create(
            session,
            item_in={"name": "Alpha", "description": None, "price": Decimal('10')},
        ),
        await repository.create(
            session,
            item_in={
                "name": "Bravo",
                "description": "alpha detail",
                "price": Decimal('20'),
            },
        ),
        await repository.create(
            session,
            item_in={"name": "Charlie", "description": "last", "price": Decimal('30')},
        ),
    ]


@pytest.mark.asyncio
async def test_create_get_all_get_by_id_update_and_delete(
    sessions: SessionFactory,
) -> None:
    repository = ItemRepository()

    async with sessions() as session, session.begin():
        item = await repository.create(
            session,
            item_in={"name": "Original", "description": None, "price": Decimal('2.5')},
        )

        assert list(await repository.get_all(session)) == [item]
        assert await repository.get_by_id(session, item.id) is item
        assert await repository.get_by_id(session, "0" * 16) is None

        assert (
            await repository.update(
                session,
                item,
                {"name": "Updated", "description": "saved", "price": Decimal('3')},
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
            ItemListQuery(
                limit=10, offset=0, min_price=Decimal('20'), sort=ItemSort.ITEM_NAME
            ),
            ["Charlie", "Bravo"],
            2,
        ),
        (
            ItemListQuery(
                limit=10, offset=0, max_price=Decimal('20'), sort=ItemSort.ITEM_NAME
            ),
            ["Bravo", "Alpha"],
            2,
        ),
        (
            ItemListQuery(
                limit=10,
                offset=0,
                min_price=Decimal('15'),
                max_price=Decimal('25'),
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
    async with sessions() as session, session.begin():
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
    async with sessions() as session, session.begin():
        await seed(session)
        items, total = await ItemRepository().find_and_count(
            session, ItemListQuery(limit=10, offset=0, sort=sort, order=order)
        )
        values = [getattr(item, sort.value) for item in items]

        assert values == sorted(values, reverse=order is SortOrder.desc)
        assert total == 3


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_owner_commit_failure_rolls_back_and_session_is_reusable(
    sessions: SessionFactory, operation: str
) -> None:
    repository = ItemRepository()

    async with sessions() as session:
        async with session.begin():
            existing = await repository.create(
                session, item_in={"name": "Before", "price": Decimal('1')}
            )

        def fail_before_commit(*_: object) -> None:
            raise RuntimeError("commit failed before COMMIT")

        event.listen(session.sync_session, "before_commit", fail_before_commit)

        try:
            with pytest.raises(RuntimeError, match="commit failed"):
                async with session.begin():
                    if operation == "create":
                        await repository.create(
                            session, item_in={"name": "Partial", "price": Decimal('99')}
                        )
                    elif operation == "update":
                        await repository.update(session, existing, {"name": "Partial"})
                    else:
                        await repository.delete(session, existing)
        finally:
            event.remove(session.sync_session, "before_commit", fail_before_commit)

        assert not session.in_transaction()
        async with session.begin():
            await repository.create(
                session, item_in={"name": "Reusable", "price": Decimal('2')}
            )

    async with sessions() as fresh:
        assert list(
            await fresh.scalars(select(ItemORM.name).order_by(ItemORM.name))
        ) == ["Before", "Reusable"]


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_owner_refresh_failure_rolls_back_and_session_is_reusable(
    sessions: SessionFactory, operation: str
) -> None:
    repository = ItemRepository()

    async with sessions() as session:
        async with session.begin():
            existing = await repository.create(
                session, item_in={"name": "Before", "price": Decimal('1')}
            )

        real_refresh = session.refresh
        session.refresh = AsyncMock(side_effect=RuntimeError("refresh failed"))

        with pytest.raises(RuntimeError, match="refresh failed"):
            async with session.begin():
                if operation == "create":
                    await repository.create(
                        session, item_in={"name": "Partial", "price": Decimal('99')}
                    )
                else:
                    await repository.update(session, existing, {"name": "Partial"})

        session.refresh = real_refresh

        assert not session.in_transaction()
        async with session.begin():
            await repository.create(
                session, item_in={"name": "Reusable", "price": Decimal('2')}
            )

    async with sessions() as fresh:
        assert list(
            await fresh.scalars(select(ItemORM.name).order_by(ItemORM.name))
        ) == ["Before", "Reusable"]


async def test_repositories_join_one_owner_and_never_commit_partially(
    sessions: SessionFactory,
) -> None:
    repository = ItemRepository()

    async with sessions() as session:
        with pytest.raises(RuntimeError, match="owner failure"):
            async with session.begin():
                item = await repository.create(
                    session, item_in={"name": "First", "price": Decimal('1')}
                )

                await repository.update(session, item, {"name": "Changed"})
                await repository.create(
                    session, item_in={"name": "Second", "price": Decimal('2')}
                )
                async with sessions() as observer:
                    assert list(await observer.scalars(select(ItemORM.name))) == []

                raise RuntimeError("owner failure")

    async with sessions() as observer:
        assert list(await observer.scalars(select(ItemORM.name))) == []


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_mutation_requires_a_caller_transaction(
    sessions: SessionFactory, operation: str
) -> None:
    repository = ItemRepository()

    async with sessions() as session:
        item = ItemORM(name="Untouched", price=Decimal('1'))

        with pytest.raises(RuntimeError, match="caller-owned transaction"):
            if operation == "create":
                await repository.create(
                    session, item_in={"name": "Rejected", "price": Decimal('1')}
                )
            elif operation == "update":
                await repository.update(session, item, {"name": "Changed"})
            else:
                await repository.delete(session, item)

        assert item.name == "Untouched"
        assert not session.in_transaction()
