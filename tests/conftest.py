import os
from collections.abc import AsyncGenerator
from pathlib import Path

os.environ.setdefault("APP_NAME", "QuickAPI")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.application import create_app
from app.config.database import Base, get_session


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


@pytest_asyncio.fixture
async def app(session: AsyncSession) -> AsyncGenerator[FastAPI, None]:
    application = create_app()

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    application.dependency_overrides[get_session] = override_session
    # Mark the application ready without touching the process-global engine.
    application.state.lifecycle._startup_started = True
    application.state.lifecycle._startup_completed = True
    yield application
    await application.state.lifecycle.shutdown()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
