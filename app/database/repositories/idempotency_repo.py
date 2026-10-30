from sqlalchemy import CursorResult, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models.idempotency_model import RETENTION_SECONDS
from app.database.entities.idempotency_orm import IdempotencyORM


class IdempotencyRepository:
    @staticmethod
    def require_transaction(session: AsyncSession) -> None:
        if not session.in_transaction():
            raise RuntimeError('Idempotency writes require an active transaction.')

    async def find(
        self, session: AsyncSession, scope_hash: str
    ) -> tuple[IdempotencyORM, bool] | None:
        self.require_transaction(session)
        row = (
            await session.execute(
                select(
                    IdempotencyORM, IdempotencyORM.expires_at > text('UTC_TIMESTAMP(3)')
                )
                .where(IdempotencyORM.scope_hash == scope_hash)
                .with_for_update()
            )
        ).one_or_none()

        return (row[0], bool(row[1])) if row else None

    async def claim(self, session: AsyncSession, record: IdempotencyORM) -> None:
        self.require_transaction(session)
        session.add(record)
        await session.flush()

    async def delete_expired(self, session: AsyncSession, scope_hash: str) -> None:
        self.require_transaction(session)
        await session.execute(
            text(
                "DELETE FROM request_idempotency WHERE scope_hash=:scope_hash AND state='completed' AND expires_at <= UTC_TIMESTAMP(3)"
            ),
            {'scope_hash': scope_hash},
        )

    async def complete(
        self, session: AsyncSession, scope_hash: str, status: int, body: bytes
    ) -> None:
        self.require_transaction(session)
        result = await session.execute(
            update(IdempotencyORM)
            .where(
                IdempotencyORM.scope_hash == scope_hash,
                IdempotencyORM.state == 'processing',
            )
            .values(
                state='completed',
                response_status=status,
                response_body=body,
                completed_at=text('UTC_TIMESTAMP(3)'),
                expires_at=text(
                    f'TIMESTAMPADD(SECOND, {RETENTION_SECONDS}, UTC_TIMESTAMP(3))'
                ),
            )
            .execution_options(synchronize_session=False)
        )

        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise RuntimeError('Only a processing idempotency claim can be completed.')

    async def purge_expired_batch(self, session: AsyncSession, limit: int) -> int:
        self.require_transaction(session)
        if not 1 <= limit <= 1000:
            raise ValueError('Idempotency cleanup batch must contain 1\u20131000 rows.')

        result = await session.execute(
            text(
                "DELETE FROM request_idempotency WHERE state='completed' AND expires_at <= UTC_TIMESTAMP(3) ORDER BY expires_at, scope_hash LIMIT :limit"
            ),
            {'limit': limit},
        )

        if not isinstance(result, CursorResult):
            raise RuntimeError('Invalid idempotency cleanup result.')

        return result.rowcount


idempotency_repo = IdempotencyRepository()
