from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[FastAPI, None]:
    """Construct the real application with an isolated, file-backed database.

    Imports deliberately live inside the fixture: the database URL must be selected
    before the application is constructed and its lifecycle services are registered.
    The database module may already have been imported by a unit test during
    collection, so its process-wide engine and session factory are replaced too.
    """
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app.config import database
    from app.config.environment import settings

    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    test_engine = create_async_engine(database_url)
    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(
        database,
        "SessionLocal",
        async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False),
    )

    from app.config.application import create_app

    application = create_app()
    application.state.e2e_database_path = tmp_path / "e2e.db"
    yield application
    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Run requests inside the application's real production lifespan."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as value:
            yield value
