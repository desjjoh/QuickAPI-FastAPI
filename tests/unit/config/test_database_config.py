import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.common.handlers.database_readiness import DatabaseReadiness
from app.config import database

pytestmark = pytest.mark.unit


class SessionContext:
    def __init__(self, session: object) -> None:
        self.session = session
        self.exited_with: tuple[object, object, object] | None = None

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        self.exited_with = (exception_type, exception, traceback)


async def test_get_session_yields_and_closes_through_context_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    context = SessionContext(session)

    monkeypatch.setattr(database, "SessionLocal", lambda: context)
    dependency = database.get_session(Request({"type": "http"}))

    assert await anext(dependency) is session
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    assert context.exited_with == (None, None, None)


async def test_get_session_propagates_error_and_context_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    context = SessionContext(session)

    monkeypatch.setattr(database, "SessionLocal", lambda: context)
    dependency = database.get_session(Request({"type": "http"}))

    await anext(dependency)
    error = RuntimeError("endpoint failed")

    with pytest.raises(RuntimeError, match="endpoint failed"):
        await dependency.athrow(error)

    assert context.exited_with is not None
    assert context.exited_with[0] is RuntimeError


async def test_init_db_checks_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock(run_sync=AsyncMock())

    @asynccontextmanager
    async def begin() -> AsyncGenerator[Mock, None]:
        yield connection

    monkeypatch.setattr(database, "engine", SimpleNamespace(connect=begin))
    await database.init_db()
    connection.run_sync.assert_awaited_once_with(database.check_revision)


async def test_init_db_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def begin() -> AsyncGenerator[None, None]:
        raise RuntimeError("unavailable")
        yield  # type: ignore[unreachable]

    dispose = AsyncMock()

    monkeypatch.setattr(
        database, "engine", SimpleNamespace(connect=begin, dispose=dispose)
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        await database.init_db()

    dispose.assert_awaited_once()


@pytest.mark.parametrize("cancel", [False, True])
async def test_startup_deadline_or_cancellation_cleans_pool(
    monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    @asynccontextmanager
    async def connect() -> AsyncGenerator[None, None]:
        entered.set()

        try:
            await asyncio.Event().wait()
            yield
        finally:
            cleaned.set()

    dispose = AsyncMock()

    monkeypatch.setattr(
        database, "engine", SimpleNamespace(connect=connect, dispose=dispose)
    )
    monkeypatch.setattr(database.settings, "DB_MIGRATION_CHECK_TIMEOUT_MS", 30)
    task = asyncio.create_task(database.init_db())

    await entered.wait()
    if cancel:
        task.cancel()

    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task

    assert cleaned.is_set()
    dispose.assert_awaited_once()
    assert await database.db_test_query() is False


async def test_connectivity_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock(execute=AsyncMock())

    @asynccontextmanager
    async def connected() -> AsyncGenerator[Mock, None]:
        yield connection

    probe = DatabaseReadiness(
        cast(AsyncEngine, SimpleNamespace(connect=connected)), cache_ms=0
    )

    probe.resume()
    monkeypatch.setattr(database, "database_readiness", probe)
    assert await database.db_test_query() is True
    connection.execute.assert_awaited_once()

    @asynccontextmanager
    async def failed() -> AsyncGenerator[None, None]:
        raise OSError("down")
        yield  # type: ignore[unreachable]

    probe = DatabaseReadiness(
        cast(AsyncEngine, SimpleNamespace(connect=failed)), cache_ms=0
    )

    probe.resume()
    monkeypatch.setattr(database, "database_readiness", probe)
    assert await database.db_test_query() is False


async def test_close_and_service_delegate_to_database_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispose = AsyncMock()

    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    await database.close_db()
    dispose.assert_awaited_once()

    start, stop, check = AsyncMock(), AsyncMock(), AsyncMock(return_value=True)

    monkeypatch.setattr(database, "init_db", start)
    monkeypatch.setattr(database, "close_db", stop)
    monkeypatch.setattr(database, "db_test_query", check)
    service = database.DatabaseService()

    await service.start()
    await service.stop()
    assert await service.check() is True
