from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config.environment import settings
from app.config.migrations import check_revision


class Base(DeclarativeBase):
    pass


def create_engine() -> AsyncEngine:
    return create_async_engine(settings.DATABASE_URL, echo=False, hide_parameters=True)


engine: AsyncEngine = create_engine()


SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.connect() as conn:
        await conn.run_sync(check_revision)


async def close_db() -> None:
    await engine.dispose()


async def db_test_query() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        return True

    except Exception:
        return False


class DatabaseService:
    name: str = "database"

    async def start(self) -> None:
        await init_db()

    async def stop(self) -> None:
        await close_db()

    async def check(self) -> bool:
        return await db_test_query()
