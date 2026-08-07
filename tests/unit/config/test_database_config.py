from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

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
    dependency = database.get_session()
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
    dependency = database.get_session()
    await anext(dependency)
    error = RuntimeError("endpoint failed")
    with pytest.raises(RuntimeError, match="endpoint failed"):
        await dependency.athrow(error)
    assert context.exited_with is not None
    assert context.exited_with[0] is RuntimeError


async def test_init_db_creates_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock(run_sync=AsyncMock())

    @asynccontextmanager
    async def begin() -> AsyncGenerator[Mock, None]:
        yield connection

    monkeypatch.setattr(database, "engine", SimpleNamespace(begin=begin))
    await database.init_db()
    connection.run_sync.assert_awaited_once_with(database.Base.metadata.create_all)


async def test_init_db_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def begin() -> AsyncGenerator[None, None]:
        raise RuntimeError("unavailable")
        yield  # type: ignore[unreachable]

    monkeypatch.setattr(database, "engine", SimpleNamespace(begin=begin))
    with pytest.raises(RuntimeError, match="unavailable"):
        await database.init_db()


async def test_connectivity_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock(execute=AsyncMock())

    @asynccontextmanager
    async def connected() -> AsyncGenerator[Mock, None]:
        yield connection

    monkeypatch.setattr(database, "engine", SimpleNamespace(connect=connected))
    assert await database.db_test_query() is True
    connection.execute.assert_awaited_once()

    @asynccontextmanager
    async def failed() -> AsyncGenerator[None, None]:
        raise OSError("down")
        yield  # type: ignore[unreachable]

    monkeypatch.setattr(database, "engine", SimpleNamespace(connect=failed))
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
