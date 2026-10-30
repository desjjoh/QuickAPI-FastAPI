# ruff: noqa: E402
# Test environment isolation must happen before application imports.
import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable, Iterator

from scripts.test_database_support import (
    clear_application_rows,
    guarded_connection,
    load_test_config,
)

# Every persistence fixture uses the explicitly guarded disposable MySQL target.
_mysql_config = load_test_config()
_backend = "mysql"

# Do not allow a developer shell or CI runner to alter collection-time settings.
os.environ.update(
    {
        "APP_NAME": "QuickAPI",
        "APP_VERSION": "1.0.0",
        "ENV": "test",
        "QUICKAPI_TEST_RUN": "true",
        "DOCS_ENABLED": "true",
        "DIAGNOSTICS_ENABLED": "true",
        "METRICS_ENABLED": "true",
        "LOG_LEVEL": "ERROR",
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "API_PUBLISHED_PORT": "8000",
        "MYSQL_PUBLISHED_PORT": "3310",
        "DATABASE_URL": _mysql_config.url.render_as_string(hide_password=False),
        "DB_POOL_CONNECTION_LIMIT": "10",
        "DB_POOL_QUEUE_LIMIT": "50",
        "DB_POOL_ACQUIRE_TIMEOUT_MS": "1000",
        "DB_CONNECT_TIMEOUT_MS": "10000",
        "DB_READINESS_TIMEOUT_MS": "1000",
        "DB_READINESS_CACHE_MS": "1000",
        "DB_MIGRATION_CHECK_TIMEOUT_MS": "5000",
        "DB_SSL": "false",
        "CORS_ORIGINS": "http://localhost:3000,https://client.test,https://client.example",
        "CORS_METHODS": "GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS",
        "CORS_ALLOWED_HEADERS": "content-type,authorization,x-requested-with",
        "CORS_EXPOSED_HEADERS": "authorization,set-cookie",
        "CORS_CREDENTIALS": "true",
        "CORS_MAX_AGE_SECONDS": "86400",
        "TRUST_PROXY": "",
        "RATE_LIMIT_WINDOW_MS": "60000",
        "RATE_LIMIT_MAX": "200",
        "RATE_LIMIT_MAX_CLIENTS": "10000",
        "REQUEST_TIMEOUT_MS": "10000",
        "HTTP_DRAIN_TIMEOUT_MS": "25000",
        "SHUTDOWN_TIMEOUT_MS": "30000",
        "REQUEST_FIRST_BODY_TIMEOUT_MS": "5000",
        "REQUEST_CHUNK_TIMEOUT_MS": "2000",
        "HTTP_MAX_BODY_BYTES": "1048576",
        "HTTP_MAX_HEADER_COUNT": "100",
        "HTTP_MAX_SINGLE_HEADER_BYTES": "4096",
        "HTTP_MAX_TOTAL_HEADER_BYTES": "8192",
        "HTTP_ALLOWED_METHODS": "GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS",
        "HTTP_ALLOWED_CONTENT_TYPES": "application/json,multipart/form-data",
    }
)
os.environ.pop("DB_SSL_CA_FILE", None)

import pytest
import pytest_asyncio
import structlog
from _pytest.terminal import TerminalReporter
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.common.handlers.lifecycle_handler import LifecycleHandler
from app.common.handlers.request_work import RequestWork
from app.common.store.request_context import RequestContext
from app.config.database_transport import build_database_engine
from app.config.metrics import REQUEST_ABORTED, REQUEST_COUNT, REQUEST_DURATION
from app.config.migrations import check_revision, upgrade_connection

_selected_database_tests = 0
_tls_tests = os.environ.get("QUICKAPI_TEST_TLS") == "true"


def pytest_asyncio_loop_factories() -> (
    dict[str, Callable[[], asyncio.AbstractEventLoop]]
):
    if _tls_tests and sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    removed = [
        item
        for item in items
        if (item.get_closest_marker("database_tls") is not None) != _tls_tests
    ]
    if removed:
        config.hook.pytest_deselected(items=removed)
        items[:] = [item for item in items if item not in removed]


def pytest_report_header() -> str:
    return f"Persistence fixture backend: {_backend}"


def pytest_collection_finish(session: pytest.Session) -> None:
    global _selected_database_tests
    _selected_database_tests = sum(
        1
        for item in session.items
        if isinstance(item, pytest.Function)
        and (
            "database_engine" in item.fixturenames
            or "migration_engine" in item.fixturenames
            or "tls_target" in item.fixturenames
        )
    )


def pytest_terminal_summary(terminalreporter: TerminalReporter) -> None:
    terminalreporter.write_line(
        f"Persistence backend: {'mysql-tls' if _tls_tests else _backend}; database-backed tests selected: {_selected_database_tests}"
    )


@pytest_asyncio.fixture
async def database_engine() -> AsyncIterator[AsyncEngine]:
    """Real MySQL commits, guarded identity, exclusive reset, isolated rows."""
    engine = build_database_engine(_mysql_config.url)
    try:
        async with guarded_connection(engine, _mysql_config) as connection:
            await connection.run_sync(check_revision)
            await connection.commit()
            await clear_application_rows(connection, _mysql_config)
            try:
                yield engine
            finally:
                await clear_application_rows(connection, _mysql_config)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def migration_engine() -> AsyncIterator[AsyncEngine]:
    """Blank disposable schema under the same live-identity and exclusive guard.

    Only fixed application/evidence tables are removed. Always restore the baseline
    before releasing the guard so later tests cannot inherit damaged history.
    """
    from sqlalchemy import text

    engine = build_database_engine(_mysql_config.url)
    try:
        async with guarded_connection(engine, _mysql_config) as connection:

            async def reset() -> None:
                for table in (
                    "migration_evidence_partial",
                    "migration_evidence_version",
                    "items",
                    "alembic_version",
                ):
                    await connection.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
                await connection.commit()

            await reset()
            try:
                yield engine
            finally:
                await reset()
                await connection.run_sync(upgrade_connection)
                await connection.commit()
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def reset_process_state() -> Iterator[None]:
    """Isolate process-wide observability and request state for every test."""
    REQUEST_COUNT.clear()
    REQUEST_DURATION.clear()
    REQUEST_ABORTED.clear()
    RequestContext.clear()
    structlog.contextvars.clear_contextvars()
    yield
    REQUEST_COUNT.clear()
    REQUEST_DURATION.clear()
    REQUEST_ABORTED.clear()
    RequestContext.clear()
    structlog.contextvars.clear_contextvars()


@pytest.fixture
def lightweight_app() -> FastAPI:
    """Provide a lifecycle-free app for unit tests that replace dependencies."""
    application = FastAPI()
    application.state.lifecycle = LifecycleHandler()
    application.state.request_work = RequestWork(25)
    return application
