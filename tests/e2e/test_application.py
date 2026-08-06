from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from sqlalchemy import inspect

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_real_lifespan_reports_readiness_before_during_and_after(
    app: FastAPI,
) -> None:
    assert app.state.lifecycle.is_ready() is False

    async with app.router.lifespan_context(app):
        assert app.state.lifecycle.is_ready() is True
        assert await app.state.lifecycle.are_all_services_healthy() is True

    assert app.state.lifecycle.is_ready() is False
    assert app.state.lifecycle.is_alive() is False


@pytest.mark.asyncio
async def test_startup_creates_database_schema(app: FastAPI) -> None:
    from app.config import database

    database_path: Path = app.state.e2e_database_path
    assert database_path.exists() is False

    async with app.router.lifespan_context(app):
        async with database.engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )

        assert "items" in tables
        assert database_path.is_file()


@pytest.mark.asyncio
async def test_shutdown_is_idempotent_and_releases_database(app: FastAPI) -> None:
    from app.config import database

    database_path: Path = app.state.e2e_database_path
    async with app.router.lifespan_context(app):
        assert await database.db_test_query() is True

    await app.state.lifecycle.shutdown()
    assert app.state.lifecycle.is_ready() is False
    assert app.state.lifecycle.is_alive() is False

    # Unlinking an open SQLite database fails on Windows.  This checks the
    # lifecycle's observable resource cleanup without depending on SQLAlchemy's
    # platform-specific pool implementation or diagnostic string.
    database_path.unlink()
    assert database_path.exists() is False


@pytest.mark.asyncio
async def test_endpoint_exception_does_not_skip_lifespan_cleanup(app: FastAPI) -> None:
    router = APIRouter()

    @router.get("/explode")
    async def explode() -> None:
        raise RuntimeError("intentional endpoint failure")

    app.include_router(router)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/explode")
            assert response.status_code == 500
            assert app.state.lifecycle.is_ready() is True

    assert app.state.lifecycle.is_ready() is False
    assert app.state.lifecycle.is_alive() is False


@pytest.mark.asyncio
async def test_partial_startup_failure_rolls_back_started_resources(
    lightweight_app: FastAPI,
) -> None:
    events: list[str] = []

    class WorkingService:
        name = "working"
        resource_open = False

        async def start(self) -> None:
            self.resource_open = True
            events.append("working:start")

        async def stop(self) -> None:
            self.resource_open = False
            events.append("working:stop")

        async def check(self) -> bool:
            return self.resource_open

    class FailingService:
        name = "failing"

        async def start(self) -> None:
            events.append("failing:start")
            raise RuntimeError("startup failed")

        async def stop(self) -> None:
            events.append("failing:stop")

        async def check(self) -> bool:
            return False

    working = WorkingService()
    lightweight_app.state.lifecycle.register([working, FailingService()])

    from app.config.application import lifespan

    with pytest.raises(RuntimeError, match="startup failed"):
        async with lifespan(lightweight_app):
            pytest.fail("a failed startup must not enter the lifespan body")

    assert events == ["working:start", "failing:start", "working:stop"]
    assert working.resource_open is False
    assert lightweight_app.state.lifecycle.is_ready() is False
    assert lightweight_app.state.lifecycle.is_alive() is False
