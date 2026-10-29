from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


@pytest_asyncio.fixture
async def app(
    database_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[FastAPI, None]:
    """Construct the real application with the selected, isolated database.

    Imports deliberately live inside the fixture: the database URL must be selected
    before the application is constructed and its lifecycle services are registered.
    The database module may already have been imported by a unit test during
    collection, so its process-wide engine and session factory are replaced too.
    """
    database_url = database_engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app.config import database
    from app.config.environment import settings

    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    test_engine = database_engine
    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(
        database,
        "SessionLocal",
        async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False),
    )

    from app.config.application import create_app

    application = create_app()
    application.state.e2e_database_backend = test_engine.dialect.name
    yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Run requests inside the application's real production lifespan."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as value:
            yield value
