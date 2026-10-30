import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config.migrations import check_revision, migration_config
from app.database.entities.idempotency_orm import IdempotencyORM

pytestmark = pytest.mark.integration


async def test_idempotency_upgrade_and_rollback_preserve_domain_data(
    migration_engine: AsyncEngine,
) -> None:
    async with migration_engine.connect() as connection:

        def migrate(
            conn: Connection, revision: str, *, downgrade: bool = False
        ) -> None:
            config = migration_config()
            config.attributes['connection'] = conn

            (command.downgrade if downgrade else command.upgrade)(config, revision)

        await connection.run_sync(lambda conn: migrate(conn, '0002_item_versions'))
        await connection.execute(
            text(
                "INSERT INTO items (id,name,price,version) VALUES ('MigrationItem001','Preserved',12.34,7)"
            )
        )
        await connection.commit()
        before = (await connection.execute(text('SELECT * FROM items'))).one()

        await connection.run_sync(lambda conn: migrate(conn, 'head'))
        await connection.commit()
        await connection.execute(
            text(
                "INSERT INTO request_idempotency (scope_hash,namespace,caller_scope,operation,route,fingerprint,state,response_status,response_body,completed_at,expires_at) VALUES (:scope,'namespace','public','widgets.create','POST /widgets',:fingerprint,'completed',201,:body,UTC_TIMESTAMP(3),TIMESTAMPADD(SECOND,86400,UTC_TIMESTAMP(3)))"
            ),
            {'scope': 'a' * 64, 'fingerprint': 'b' * 64, 'body': b'{ "value": 1 }'},
        )
        await connection.commit()
        await connection.run_sync(lambda conn: migrate(conn, 'head'))
        assert (
            await connection.execute(
                text('SELECT response_body FROM request_idempotency')
            )
        ).scalar_one() == b'{ "value": 1 }'
        assert (await connection.execute(text('SELECT * FROM items'))).one() == before
        assert (
            await connection.run_sync(
                lambda conn: compare_metadata(
                    MigrationContext.configure(conn), IdempotencyORM.metadata
                )
            )
            == []
        )
        await connection.run_sync(
            lambda conn: migrate(conn, '0002_item_versions', downgrade=True)
        )
        await connection.commit()
        assert 'request_idempotency' not in await connection.run_sync(
            lambda conn: inspect(conn).get_table_names()
        )
        assert (await connection.execute(text('SELECT * FROM items'))).one() == before
        with pytest.raises(RuntimeError, match='schema revision is not current'):
            await connection.run_sync(check_revision)

        await connection.run_sync(lambda conn: migrate(conn, 'head'))
        await connection.commit()
        assert (
            await connection.execute(text('SELECT COUNT(*) FROM request_idempotency'))
        ).scalar_one() == 0
        assert (await connection.execute(text('SELECT * FROM items'))).one() == before
        await connection.run_sync(check_revision)
