from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest_asyncio.fixture
async def session(database_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Use the selected backend with real commits and isolated application rows."""
    factory = async_sessionmaker(database_engine, expire_on_commit=False)

    async with factory() as value:
        yield value
