"""Fail-closed configuration and live identity checks for disposable MySQL tests."""

import os
import re
import sys
import tempfile
from collections.abc import AsyncGenerator, Generator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

ROOT = Path(__file__).resolve().parents[1]
LOCK_NAME = "quickapi_fastapi_disposable_tests"


@contextmanager
def command_lock() -> Generator[None, None, None]:
    """Keep another local wrapper from tearing down infrastructure during a run."""
    path = Path(tempfile.gettempdir()) / "quickapi-fastapi-test-command.lock"

    with path.open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()

        lock.seek(0)

        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError(
                "Another disposable test command is active; infrastructure was not changed."
            ) from None

        try:
            yield
        finally:
            lock.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class TestDatabaseConfig:
    url: URL
    database: str
    user: str
    values: dict[str, str] = field(repr=False)


def load_test_config(
    environment: Mapping[str, str] | None = None, path: Path | None = None
) -> TestDatabaseConfig:
    """Load only .env.test plus explicit overrides; never consult development .env."""
    source = os.environ if environment is None else environment

    if source.get("PYTEST_XDIST_WORKER"):
        raise ValueError(
            "MySQL test fixtures require serial execution, without xdist workers."
        )

    values = {
        key: value
        for key, value in dotenv_values(
            path or ROOT / ".env.test", interpolate=False
        ).items()
        if value is not None
    }

    for key, value in source.items():
        if key.startswith(("TEST_", "DB_")) or key == "ENV":
            values[key] = value

    if values.get("ENV") != "test" or values.get("TEST_DB_ENABLED") != "true":
        raise ValueError(
            "Disposable database commands require ENV=test and TEST_DB_ENABLED=true."
        )

    database = values.get("TEST_DB_DATABASE", "")

    if not re.fullmatch(r"quickapi_fastapi_disposable_test(?:_[a-z0-9]+)?", database):
        raise ValueError("The database must use the FastAPI disposable-test name.")

    user = values.get("TEST_DB_USER", "")

    if user != "quickapi_fastapi_test":
        raise ValueError("A dedicated non-root FastAPI test database user is required.")

    try:
        url = make_url(values["TEST_DATABASE_URL"])
        raw_port = values["TEST_MYSQL_PORT"]

        if not re.fullmatch(r"[0-9]+", raw_port):
            raise ValueError("Invalid test port.")

        port = int(raw_port)
        valid = (
            url.drivername == "mysql+asyncmy"
            and url.database == database
            and url.username == user
            and bool(values.get("TEST_DB_PASSWORD"))
            and url.password == values["TEST_DB_PASSWORD"]
            and url.port == port
            and 1 <= port <= 65535
            and not url.query
        )
    except (ArgumentError, KeyError, TypeError, ValueError):
        raise ValueError("Invalid disposable MySQL connection configuration.") from None

    allowed = {"127.0.0.1", "localhost", "::1", "mysql-test", "mysql-tls-test"}

    allowed.update(
        x.strip().lower()
        for x in values.get("TEST_DB_ALLOWED_HOSTS", "").split(",")
        if x.strip()
    )
    if not valid or (url.host or "").lower() not in allowed:
        raise ValueError(
            "Disposable MySQL URL does not match the permitted test target."
        )

    return TestDatabaseConfig(url, database, user, values)


def assert_test_engine(engine: AsyncEngine, config: TestDatabaseConfig) -> None:
    if engine.url != config.url:
        raise ValueError(
            "Active engine does not match the validated disposable test connection."
        )


@asynccontextmanager
async def guarded_connection(
    engine: AsyncEngine, config: TestDatabaseConfig
) -> AsyncGenerator[AsyncConnection, None]:
    """Verify live identity and exclude simultaneous writers before destructive SQL."""
    assert_test_engine(engine, config)
    async with engine.connect() as connection:
        database, user = (
            await connection.execute(text("SELECT DATABASE(), CURRENT_USER()"))
        ).one()

        if database != config.database or str(user).split("@", 1)[0] != config.user:
            raise ValueError(
                "Connected database/user differs from the disposable test identity."
            )

        locked = (
            await connection.execute(
                text("SELECT GET_LOCK(:name, 0)"), {"name": LOCK_NAME}
            )
        ).scalar_one()

        await connection.commit()
        if locked != 1:
            raise RuntimeError(
                "Disposable test database is already in use by another command/test."
            )

        try:
            yield connection
        finally:
            await connection.rollback()
            await connection.execute(
                text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME}
            )
            await connection.commit()


async def clear_application_rows(
    connection: AsyncConnection, config: TestDatabaseConfig
) -> None:
    """Recheck the active target before every reset; preserve migration history."""
    assert_test_engine(connection.engine, config)
    database, user = (
        await connection.execute(text("SELECT DATABASE(), CURRENT_USER()"))
    ).one()

    if database != config.database or str(user).split("@", 1)[0] != config.user:
        raise ValueError(
            "Refusing reset: connected database/user is not the test identity."
        )

    await connection.execute(text("DELETE FROM items"))
    await connection.commit()
