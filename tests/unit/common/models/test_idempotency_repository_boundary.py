import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.entities.idempotency_orm import IdempotencyORM
from app.database.repositories.idempotency_repo import IdempotencyRepository

pytestmark = pytest.mark.unit


async def test_repository_operations_require_caller_owned_transactions() -> None:
    repository = IdempotencyRepository()

    async with AsyncSession(autobegin=False) as session:
        for operation in [
            repository.find(session, 'a' * 64),
            repository.claim(session, IdempotencyORM()),
            repository.delete_expired(session, 'a' * 64),
            repository.complete(session, 'a' * 64, 201, b'{}'),
            repository.purge_expired_batch(session, 1),
        ]:
            with pytest.raises(RuntimeError, match='active transaction'):
                await operation


async def test_cleanup_batch_bounds_fail_before_database_access() -> None:
    repository = IdempotencyRepository()

    async with AsyncSession(autobegin=False) as session, session.begin():
        for limit in (0, 1001):
            with pytest.raises(ValueError, match='batch'):
                await repository.purge_expired_batch(session, limit)
