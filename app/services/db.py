from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import log


DATABASE_URL = "sqlite+aiosqlite:///./app.db"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    echo_pool=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    future=True,    
)


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app.api.items.models.db_models import ItemORM

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        log.info("Database initialized", url=str(engine.url), service=settings.app_name)

    except Exception as e:
        log.error("Database initialization failed", error=str(e))
        raise


async def close_db() -> None:
    await engine.dispose()
    log.info("Database connection closed", service=settings.app_name)
