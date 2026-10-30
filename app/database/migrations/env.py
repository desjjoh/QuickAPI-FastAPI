"""Alembic uses the application's async driver and DATABASE_URL."""

from alembic import context
from sqlalchemy.engine import Connection

from app.config.database_transport import build_database_engine
from app.config.environment import settings
from app.config.event_loop import run_database
from app.database.entities.idempotency_orm import IdempotencyORM as IdempotencyORM
from app.database.entities.item_orm import ItemORM

config = context.config
target_metadata = ItemORM.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = build_database_engine(settings.DATABASE_URL)

    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run_migrations(config.attributes["connection"])
else:
    run_database(run_async_migrations())
