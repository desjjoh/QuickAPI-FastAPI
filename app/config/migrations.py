"""Shared migration configuration and read-only startup revision checks."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

from app.config.logging import log


def migration_config() -> Config:
    return Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))


def upgrade_connection(connection: Connection) -> None:
    """Apply migrations explicitly using an existing connection (also used by tests)."""
    config = migration_config()
    config.attributes["connection"] = connection

    command.upgrade(config, "head")


def check_revision(connection: Connection) -> None:
    config = migration_config()
    heads = ScriptDirectory.from_config(config).get_heads()
    current = MigrationContext.configure(connection).get_current_heads()

    if len(heads) != 1 or set(current) != set(heads):
        log.error(
            "Database schema revision is not current. Run python -m alembic upgrade head."
        )

        raise RuntimeError(
            "Database schema revision is not current. Run python -m alembic upgrade head."
        )
