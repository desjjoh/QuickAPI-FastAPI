import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from scripts import test_database_support, test_db
from scripts.test_database_support import (
    clear_application_rows,
    command_lock,
    guarded_connection,
    load_test_config,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "overrides",
    [
        {"ENV": "production"},
        {"ENV": "development"},
        {"TEST_DB_ENABLED": "false"},
        {"TEST_DB_ENABLED": "TRUE"},
        {"TEST_DB_ENABLED": ""},
        {"TEST_DB_DATABASE": "quickapi-fastapi-dev"},
        {"TEST_DB_DATABASE": "quickapi_disposable_test"},
        {"TEST_DB_DATABASE": "mysql"},
        {"TEST_DB_USER": "root"},
        {"TEST_DB_USER": "quickapi"},
        {"TEST_DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test"},
        {"TEST_DATABASE_URL": "not-a-url"},
        {
            "TEST_DATABASE_URL": "mysql+asyncmy://root:password@127.0.0.1:3311/quickapi_fastapi_disposable_test"
        },
        {
            "TEST_DATABASE_URL": "mysql+asyncmy://quickapi_fastapi_test:quickapi_fastapi_test_password@db.example:3311/quickapi_fastapi_disposable_test"
        },
        {
            "TEST_DATABASE_URL": "mysql+asyncmy://quickapi_fastapi_test:quickapi_fastapi_test_password@127.0.0.1:3310/quickapi-fastapi-dev"
        },
        {"TEST_MYSQL_PORT": "0"},
        {"TEST_MYSQL_PORT": "65536"},
        {"TEST_MYSQL_PORT": "invalid"},
        {"TEST_MYSQL_PORT": " 3311"},
        {"PYTEST_XDIST_WORKER": "gw0"},
        {"TEST_DB_PASSWORD": "wrong"},
    ],
)
def test_unsafe_targets_are_rejected(overrides: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        load_test_config(overrides)


def test_development_url_is_never_used_and_defaults_are_explicit() -> None:
    config = load_test_config(
        {"DATABASE_URL": "mysql+asyncmy://root:secret@localhost/dev"}
    )

    assert config.database == "quickapi_fastapi_disposable_test"
    assert config.url.port == 3311 and config.user == "quickapi_fastapi_test"


@pytest.mark.parametrize(
    "identity",
    [
        ("quickapi-fastapi-dev", "quickapi_fastapi_test@%"),
        ("quickapi_fastapi_disposable_test", "root@%"),
    ],
)
async def test_live_identity_mismatch_prevents_lock_and_destructive_sql(
    identity: tuple[str, str],
) -> None:
    config = load_test_config({})
    engine = Mock(spec=AsyncEngine, url=config.url)
    connection = AsyncMock(spec=AsyncConnection)
    connection.execute.return_value = Mock(one=Mock(return_value=identity))
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="identity"):
        async with guarded_connection(engine, config):
            pytest.fail("Unsafe live identity must not be admitted")

    assert connection.execute.await_count == 1


async def test_engine_mismatch_is_rejected_before_connection() -> None:
    engine = Mock(
        spec=AsyncEngine, url=make_url("postgresql+asyncpg://test:test@localhost/test")
    )

    with pytest.raises(ValueError, match="Active engine"):
        async with guarded_connection(engine, load_test_config({})):
            pytest.fail("Unsafe engine must not be admitted")

    engine.connect.assert_not_called()


@pytest.mark.parametrize("locked", [0, None])
async def test_busy_database_is_rejected_without_reset(locked: int | None) -> None:
    config = load_test_config({})
    engine = Mock(spec=AsyncEngine, url=config.url)
    connection = AsyncMock(spec=AsyncConnection)
    connection.execute.side_effect = [
        Mock(one=Mock(return_value=(config.database, config.user + "@%"))),
        Mock(scalar_one=Mock(return_value=locked)),
    ]
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="already in use"):
        async with guarded_connection(engine, config):
            pytest.fail("A busy database must not be reset")

    assert connection.execute.await_count == 2


async def test_lock_is_released_after_test_failure() -> None:
    config = load_test_config({})
    engine = Mock(spec=AsyncEngine, url=config.url)
    connection = AsyncMock(spec=AsyncConnection)
    connection.execute.side_effect = [
        Mock(one=Mock(return_value=(config.database, config.user + "@%"))),
        Mock(scalar_one=Mock(return_value=1)),
        Mock(),
    ]
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="test failed"):
        async with guarded_connection(engine, config):
            raise RuntimeError("test failed")

    assert "RELEASE_LOCK" in str(connection.execute.await_args_list[-1].args[0])
    connection.rollback.assert_awaited_once()


async def test_reset_rechecks_connected_identity_before_delete() -> None:
    config = load_test_config({})
    connection = AsyncMock(spec=AsyncConnection)
    connection.engine = Mock(spec=AsyncEngine, url=config.url)
    connection.execute.return_value = Mock(one=Mock(return_value=("mysql", "root@%")))

    with pytest.raises(ValueError, match="Refusing reset"):
        await clear_application_rows(connection, config)

    assert connection.execute.await_count == 1


def test_rejected_cli_configuration_does_not_expose_credentials() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.test_db", "current"],
        env={
            **os.environ,
            "TEST_DATABASE_URL": "mysql+asyncmy://root:private-value-never-log@localhost/dev",
        },
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    assert "private-value-never-log" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_competing_command_is_rejected_before_touching_infrastructure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        test_database_support.tempfile, "gettempdir", lambda: str(tmp_path)
    )
    with command_lock():
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from scripts import test_db; import sys; test_db.compose=lambda *args: (_ for _ in ()).throw(AssertionError('Infrastructure was touched')); sys.argv=['test_db','down']; test_db.main()",
            ],
            env={
                **os.environ,
                "TMPDIR": str(tmp_path),
                "TEMP": str(tmp_path),
                "TMP": str(tmp_path),
            },
            capture_output=True,
            text=True,
            timeout=10,
        )

    assert (
        result.returncode == 1
        and "Another disposable test command is active" in result.stderr
    )


def test_command_lock_releases_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        test_database_support.tempfile, "gettempdir", lambda: str(tmp_path)
    )
    with pytest.raises(RuntimeError):
        with command_lock():
            raise RuntimeError("test failed")

    with command_lock():
        pass


def test_migration_failure_still_collects_logs_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, ...]] = []

    def compose(config: object, *args: str) -> int:
        events.append(args)

        return 0

    monkeypatch.setattr(test_db, "compose", compose)
    monkeypatch.setattr(
        test_db, "migration", AsyncMock(side_effect=RuntimeError("migration failed"))
    )
    args = argparse.Namespace(action="test", layer="integration", keep_db=False)

    with pytest.raises(RuntimeError, match="migration failed"):
        test_db.dispatch(load_test_config({}), args)

    assert events[0][0] == "up"
    assert events[1][0] == "logs" and events[2] == ("down", "--volumes")


@pytest.mark.parametrize("collected,test_result", [(5, 0), (0, 1), (0, 0)])
def test_collection_and_test_exit_codes_preserve_cleanup(
    collected: int, test_result: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, ...]] = []

    def compose(config: object, *args: str) -> int:
        events.append(args)

        return 0

    monkeypatch.setattr(test_db, "compose", compose)
    monkeypatch.setattr(test_db, "migration", AsyncMock())
    monkeypatch.setattr(
        test_db.subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                [], collected, stdout="collection result"
            )
        ),
    )
    called = Mock(return_value=test_result)

    monkeypatch.setattr(test_db.subprocess, "call", called)
    args = argparse.Namespace(action="test", layer="integration", keep_db=False)

    assert test_db.dispatch(load_test_config({}), args) == (collected or test_result)
    assert called.call_count == (0 if collected else 1)
    assert events[-1] == ("down", "--volumes")
    assert any(event[0] == "logs" for event in events) == bool(collected or test_result)


def test_unavailable_mysql_fails_without_fallback(tmp_path: Path) -> None:
    # Reserve a loopback port without a listener, proving no MySQL can answer it.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        config = load_test_config({})
        url = config.url.set(port=port).render_as_string(hide_password=False)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-cov",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(tmp_path / "child"),
                "tests/integration/database/test_database_isolation.py::test_selected_database_starts_clean_with_migration_history",
            ],
            env={
                **os.environ,
                "QUICKAPI_TEST_RUN": "true",
                "TEST_MYSQL_PORT": str(port),
                "TEST_DATABASE_URL": url,
            },
            capture_output=True,
            text=True,
            timeout=30,
        )

    assert result.returncode == 1
    assert "Persistence backend: mysql" in result.stdout
    assert "1 error" in result.stdout


def test_selected_mysql_settings_ignore_development_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config.environment import load_settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUICKAPI_TEST_RUN", "true")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("HTTP_MAX_BODY_BYTES", raising=False)
    (tmp_path / ".env").write_text("HTTP_MAX_BODY_BYTES=-1\n")
    assert load_settings().HTTP_MAX_BODY_BYTES == 1048576
