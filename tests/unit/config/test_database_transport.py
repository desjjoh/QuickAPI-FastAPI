import asyncio
import ssl
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.common.handlers.database_pool import Admission, DatabaseUnavailableError
from app.config.database_transport import (
    DatabasePolicy,
    build_database_engine,
    tls_context,
)
from app.config.environment import Settings

pytestmark = pytest.mark.unit


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, APP_NAME="test", APP_VERSION="1.0.0", ENV="test", PORT=8000, DATABASE_URL="mysql+asyncmy://test:test@localhost/test", **overrides)  # type: ignore


@pytest.mark.parametrize(
    "key",
    [
        "DB_POOL_CONNECTION_LIMIT",
        "DB_POOL_QUEUE_LIMIT",
        "DB_POOL_ACQUIRE_TIMEOUT_MS",
        "DB_CONNECT_TIMEOUT_MS",
        "DB_READINESS_TIMEOUT_MS",
        "DB_READINESS_CACHE_MS",
        "DB_MIGRATION_CHECK_TIMEOUT_MS",
    ],
)
@pytest.mark.parametrize("value", ["", " ", "1.5", "-1", True, "0x10"])
def test_database_numbers_are_strict(key: str, value: object) -> None:
    with pytest.raises(ValidationError):
        settings(**{key: value})


@pytest.mark.parametrize(
    "values",
    [
        {"DB_POOL_CONNECTION_LIMIT": 0},
        {"DB_POOL_CONNECTION_LIMIT": 1001},
        {"DB_POOL_QUEUE_LIMIT": 10001},
        {"DB_CONNECT_TIMEOUT_MS": 0},
        {"DB_POOL_ACQUIRE_TIMEOUT_MS": 0},
        {"DB_SSL": "TRUE"},
        {"DB_SSL_CA_FILE": ""},
        {"DB_SSL_CA_FILE": "missing.pem"},
        {"DB_SSL": True, "DB_SSL_CA_FILE": "missing.pem"},
    ],
)
def test_invalid_database_configuration_fails(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        settings(**values)


def test_database_defaults_and_tls_context(tmp_path: Path) -> None:
    config = settings(DB_POOL_QUEUE_LIMIT=0)
    assert config.DB_POOL_CONNECTION_LIMIT == 10 and config.DB_POOL_QUEUE_LIMIT == 0
    context = tls_context(DatabasePolicy(ssl_enabled=True))
    assert context is not None and context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    bad = tmp_path / 'invalid.pem'
    bad.write_text('not a certificate')
    with pytest.raises(ValueError, match="CA certificates"):
        tls_context(DatabasePolicy(ssl_enabled=True, ca_file=str(bad)))
    with pytest.raises(ValueError, match="requires DB_SSL"):
        tls_context(DatabasePolicy(ca_file=str(bad)))
    with pytest.raises(ValueError, match="require MySQL"):
        build_database_engine(
            'sqlite+aiosqlite:///:memory:', policy=DatabasePolicy(ssl_enabled=True)
        )
    with pytest.raises(ValueError, match="only the charset"):
        build_database_engine(
            'mysql+asyncmy://x:x@localhost/test?ssl=false', policy=DatabasePolicy()
        )


async def test_admission_fifo_capacity_cancel_handoff_and_close() -> None:
    gate = Admission(1, 2)
    await gate.acquire()
    first = asyncio.create_task(gate.acquire())
    second = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    with pytest.raises(DatabaseUnavailableError) as full:
        await gate.acquire()
    assert full.value.code == 'DB_POOL_CAPACITY'
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    gate.release()
    await second
    assert gate.active == 1 and not gate.waiters
    third = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    gate.close()
    with pytest.raises(DatabaseUnavailableError) as closed:
        await third
    assert closed.value.code == 'DB_POOL_CLOSED'
    gate.release()
    assert gate.active == 0
    with pytest.raises(DatabaseUnavailableError):
        await gate.acquire()


async def test_cancel_after_slot_handoff_returns_capacity() -> None:
    gate = Admission(1, 1)
    await gate.acquire()
    task = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    gate.release()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gate.active == 0


def test_windows_tls_entrypoints_choose_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import event_loop
    from app.config.environment import settings as configured

    monkeypatch.setattr(event_loop.sys, "platform", "win32")
    monkeypatch.setattr(configured, "DB_SSL", True)
    assert event_loop.database_loop_factory() is asyncio.SelectorEventLoop
    loop = event_loop.server_loop_factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()


async def test_tls_cipher_absence_is_rejected_without_plaintext_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.config import database_transport

    cursor = AsyncMock()
    cursor.fetchone.return_value = ('Ssl_cipher', '')
    connection = Mock(connect=AsyncMock(), close=Mock())
    connection.cursor.return_value.__aenter__ = AsyncMock(return_value=cursor)
    connection.cursor.return_value.__aexit__ = AsyncMock(return_value=None)
    driver = SimpleNamespace(Connection=Mock(return_value=connection))

    def import_driver(name: str) -> SimpleNamespace:
        return driver

    monkeypatch.setattr(
        database_transport,
        'importlib',
        SimpleNamespace(import_module=import_driver),
    )
    engine = build_database_engine(
        'mysql+asyncmy://test:private-value-never-log@localhost/test',
        policy=DatabasePolicy(ssl_enabled=True),
    )
    try:
        with pytest.raises(DatabaseUnavailableError) as error:
            await engine.connect()
        assert error.value.code == 'DB_TLS_REQUIRED'
        assert 'private-value-never-log' not in str(error.value)
        connection.close.assert_called_once()
    finally:
        await engine.dispose()
