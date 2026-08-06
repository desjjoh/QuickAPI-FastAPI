from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.entities.item_orm import ItemORM
from app.database.repositories.item_repo import ItemRepository


@pytest.mark.asyncio
async def test_repository_commits_crud(session: AsyncSession) -> None:
    repo = ItemRepository()
    item = await repo.create(session, item_in={"name": "Committed", "price": 2.5})
    assert (await session.scalar(select(ItemORM).where(ItemORM.id == item.id))) is item
    await repo.update(session, item, {"name": "Updated"})
    assert item.name == "Updated"
    await repo.delete(session, item)
    assert await session.scalar(select(ItemORM).where(ItemORM.id == item.id)) is None


@pytest.mark.asyncio
async def test_failed_commit_can_be_rolled_back(session: AsyncSession) -> None:
    repo = ItemRepository()
    session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    with pytest.raises(RuntimeError, match="commit failed"):
        await repo.create(session, item_in={"name": "No commit", "price": 1})
    session.commit.side_effect = None
    await session.rollback()
    assert await session.scalar(select(ItemORM)) is None
