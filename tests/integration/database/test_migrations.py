import io
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import database
from app.config.environment import settings
from app.config.migrations import check_revision, migration_config, upgrade_connection
from app.database.entities.item_orm import ItemORM

pytestmark = pytest.mark.integration


async def test_empty_database_is_rejected_without_creating_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(database, "engine", engine)
    try:
        with pytest.raises(RuntimeError, match="python -m alembic upgrade head"):
            await database.init_db()
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda conn: inspect(conn).get_table_names()
            )
        assert tables == []
    finally:
        await engine.dispose()


async def test_baseline_matches_models_and_repeated_upgrade_preserves_data(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'baseline.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_connection)
            await connection.execute(
                text(
                    "INSERT INTO items (id, name, price) VALUES ('sample', 'Sample', 12.34)"
                )
            )
            await connection.run_sync(upgrade_connection)
            await connection.run_sync(check_revision)
            assert (
                await connection.execute(text("SELECT name FROM items"))
            ).scalar_one() == "Sample"

            def compare(conn: Connection) -> None:
                assert (
                    compare_metadata(MigrationContext.configure(conn), ItemORM.metadata)
                    == []
                )

            await connection.run_sync(compare)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("revision", [None, "unknown_revision", "older_revision"])
async def test_missing_or_incompatible_history_is_rejected(
    tmp_path: Path, revision: str | None
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'history.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_connection)
            await connection.execute(text("DELETE FROM alembic_version"))
            if revision is not None:
                await connection.execute(
                    text(
                        "INSERT INTO alembic_version (version_num) VALUES (:revision)"
                    ),
                    {"revision": revision},
                )
            with pytest.raises(RuntimeError, match="schema revision is not current"):
                await connection.run_sync(check_revision)
    finally:
        await engine.dispose()


async def test_baseline_can_be_removed_and_reapplied_on_disposable_database(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reset.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_connection)

            def downgrade(conn: Connection) -> None:
                config = migration_config()
                config.attributes["connection"] = conn
                command.downgrade(config, "base")
                assert "items" not in inspect(conn).get_table_names()

            await connection.run_sync(downgrade)
            await connection.run_sync(upgrade_connection)
            await connection.run_sync(check_revision)
    finally:
        await engine.dispose()


def test_offline_sql_contains_baseline_and_version_history() -> None:
    output = io.StringIO()
    config = migration_config()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    assert "CREATE TABLE items" in output.getvalue()
    assert "0001_create_items" in output.getvalue()


def test_online_commands_use_configured_async_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'online.db'}"
    )
    config = migration_config()
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
