from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config.migrations import check_revision
from scripts.test_database_support import guarded_connection, load_test_config

pytestmark = pytest.mark.integration


async def test_selected_backend_identity_and_concurrent_reset_exclusion(
    database_engine: AsyncEngine,
) -> None:
    if database_engine.dialect.name == "mysql":
        config = load_test_config()
        async with database_engine.connect() as connection:
            identity = (
                await connection.execute(text("SELECT DATABASE(), CURRENT_USER()"))
            ).one()
            assert identity[0] == config.database
            assert str(identity[1]).split("@", 1)[0] == config.user
        with pytest.raises(RuntimeError, match="already in use"):
            async with guarded_connection(database_engine, config):
                pytest.fail("A second connection must not enter the held test lock")
    else:
        assert database_engine.url.database is not None
        assert Path(database_engine.url.database).is_file()


async def test_selected_database_starts_clean_with_migration_history(
    database_engine: AsyncEngine,
) -> None:
    async with database_engine.connect() as connection:
        await connection.run_sync(check_revision)
        assert (
            await connection.execute(text("SELECT COUNT(*) FROM items"))
        ).scalar_one() == 0


async def test_real_commit_is_visible_on_fresh_connection_and_constraints_hold(
    database_engine: AsyncEngine,
) -> None:
    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO items (id,name,price) VALUES ('committed','Committed',12.34)"
            )
        )
    async with database_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT name,price,createdAt,updatedAt FROM items WHERE id='committed'"
                )
            )
        ).one()
        assert row[0] == "Committed" and float(row[1]) == 12.34
        assert row[2] is not None and row[3] is not None
    with pytest.raises(IntegrityError):
        async with database_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO items (id,name,price) VALUES ('committed','Duplicate',2)"
                )
            )
    async with database_engine.connect() as connection:
        assert (
            await connection.execute(text("SELECT COUNT(*) FROM items"))
        ).scalar_one() == 1


async def test_sqlite_engine_disposal_releases_database_file(tmp_path: Path) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    path = tmp_path / "disposal.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
    path.unlink()
    assert not path.exists()
