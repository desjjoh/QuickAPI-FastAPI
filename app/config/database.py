import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from app.common.handlers.database_readiness import DatabaseReadiness
from app.config.database_transport import build_database_engine
from app.config.environment import settings
from app.config.migrations import check_revision


class Base(DeclarativeBase):
    pass


def create_engine() -> AsyncEngine:
    return build_database_engine(settings.DATABASE_URL)


engine: AsyncEngine = create_engine()
database_readiness = DatabaseReadiness(
    engine, settings.DB_READINESS_TIMEOUT_MS, settings.DB_READINESS_CACHE_MS
)


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
    try:
        async with asyncio.timeout(settings.DB_MIGRATION_CHECK_TIMEOUT_MS / 1000):
            async with engine.connect() as conn:
                await conn.run_sync(check_revision)
        database_readiness.resume()
    except BaseException:
        await database_readiness.stop()
        await engine.dispose()
        raise


async def close_db() -> None:
    await database_readiness.stop()
    await engine.dispose()


async def db_test_query() -> bool:
    return await database_readiness.check()


class DatabaseService:
    name: str = "database"

    async def start(self) -> None:
        await init_db()

    async def stop(self) -> None:
        await close_db()

    async def check(self) -> bool:
        return await db_test_query()
