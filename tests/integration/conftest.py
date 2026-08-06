from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.database import Base


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated real SQLite session for repository integration tests."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value

    await engine.dispose()
