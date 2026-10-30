"""Request-owned durable JSON execution; domain services remain unaware of retries."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, NoReturn

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.common.handlers.request_activity import request_activity
from app.common.models.idempotency_model import IdempotencyPolicy, digest
from app.config.environment import settings
from app.config.logging import log
from app.database.entities.idempotency_orm import IdempotencyORM
from app.database.repositories.idempotency_repo import idempotency_repo


class PreparedJSONResponse(JSONResponse):
    def __init__(self, body: bytes, status: int) -> None:
        # Never serialize a replay again: retain the original JSON bytes.
        Response.__init__(
            self, content=body, status_code=status, media_type='application/json'
        )

    def render(self, content: Any) -> bytes:
        if not isinstance(content, bytes):
            raise RuntimeError('An idempotency replay requires prepared bytes.')

        return content


@dataclass
class IdempotencyExecution:
    request: Request
    session: AsyncSession
    connection: AsyncConnection
    policy: IdempotencyPolicy
    key: str
    scope_hash: str | None = None
    locked: bool = False
    uncertain: bool = False
    claimed: bool = False

    async def begin(self, inputs: dict[str, Any]) -> PreparedJSONResponse | None:
        activity = request_activity(self.request.scope)

        activity.assert_active()
        caller = (
            self.policy.caller_scope(self.request)
            if callable(self.policy.caller_scope)
            else self.policy.caller_scope
        )

        if not 1 <= len(caller) <= 128:
            raise RuntimeError(
                'Idempotency caller scope must contain 1\u2013128 characters.'
            )

        namespace = digest([settings.APP_NAME, self.connection.engine.url.database])
        self.scope_hash = digest(
            [
                'idempotency-v1',
                namespace,
                caller,
                self.policy.operation,
                self.policy.route,
                self.key,
            ]
        )
        fingerprint = digest(inputs)
        self.uncertain = True
        acquired = await self.session.scalar(
            text('SELECT GET_LOCK(:name, 0)'), {'name': self.scope_hash}
        )

        if acquired not in (0, 1):
            raise RuntimeError('Unable to establish idempotency lock ownership.')

        self.uncertain = False

        if acquired == 0:
            raise HTTPException(409, 'This idempotent request is already processing.')

        self.locked = True

        activity.assert_active()
        existing = await idempotency_repo.find(self.session, self.scope_hash)

        if existing:
            record, unexpired = existing

            if record.state != 'completed':
                raise RuntimeError('Unexpected persisted idempotency claim state.')

            if unexpired:
                if record.fingerprint != fingerprint:
                    raise HTTPException(
                        409,
                        'Idempotency-Key was already used with a different payload.',
                    )

                if record.response_status is None or record.response_body is None:
                    raise RuntimeError('Stored idempotency response is incomplete.')

                validate_response(record.response_status, record.response_body, 65536)

                return PreparedJSONResponse(
                    record.response_body, record.response_status
                )

            await idempotency_repo.delete_expired(self.session, self.scope_hash)
            self.session.expunge(record)

        await idempotency_repo.claim(
            self.session,
            IdempotencyORM(
                scope_hash=self.scope_hash,
                namespace=namespace,
                caller_scope=caller,
                operation=self.policy.operation,
                route=self.policy.route,
                fingerprint=fingerprint,
                state='processing',
            ),
        )
        self.claimed = True

        activity.assert_active()

        return None

    async def complete(self, response: JSONResponse) -> None:
        if self.claimed:
            request_activity(self.request.scope).assert_active()
            if self.scope_hash is None:
                raise RuntimeError('Missing idempotency scope.')

            body = bytes(response.body)

            validate_response(
                response.status_code, body, settings.IDEMPOTENCY_MAX_RESPONSE_BYTES
            )
            await idempotency_repo.complete(
                self.session, self.scope_hash, response.status_code, body
            )

    async def release(self, failed: bool) -> None:
        try:
            if (
                self.uncertain
                or self.connection.invalidated
                or self.connection.in_transaction()
            ):
                await self.connection.invalidate()

                return

            if self.locked:
                released = await self.connection.scalar(
                    text('SELECT RELEASE_LOCK(:name)'), {'name': self.scope_hash}
                )

                if released != 1:
                    raise RuntimeError('Unable to confirm idempotency lock release.')
        except BaseException as exc:
            await self.connection.invalidate()
            if not failed:
                raise

            log.error('Idempotency session cleanup failed.', error=exc)
        finally:
            if failed and not self.connection.invalidated:
                await self.connection.invalidate()


def validate_response(status: int, body: bytes, limit: int) -> None:
    if not 200 <= status < 300 or len(body) > limit:
        raise RuntimeError(
            'Prepared response exceeds the idempotency storage contract.'
        )

    if status in (204, 205):
        if body:
            raise RuntimeError('Bodyless idempotent responses must not contain JSON.')
    else:

        def invalid_constant(value: str) -> NoReturn:
            raise ValueError('Prepared response must contain valid JSON.')

        json.loads(body.decode('utf-8'), parse_constant=invalid_constant)


execution_context: ContextVar[IdempotencyExecution | None] = ContextVar(
    'idempotency_execution', default=None
)


@asynccontextmanager
async def pinned_execution(
    session: AsyncSession, request: Request, policy: IdempotencyPolicy, key: str
) -> AsyncGenerator[IdempotencyExecution, None]:
    engine = session.bind

    if not isinstance(engine, AsyncEngine):
        raise RuntimeError(
            'Idempotent HTTP execution requires a request-owned engine session.'
        )

    async with engine.connect() as connection:
        # Pin the same physical connection across COMMIT and advisory-lock release.
        # Rebinding is only permitted before this fresh request starts a transaction.
        session.bind = connection
        session.sync_session.bind = connection.sync_connection
        execution = IdempotencyExecution(request, session, connection, policy, key)
        failed = True

        try:
            yield execution
            failed = False
        finally:
            try:
                await execution.release(failed)
            finally:
                session.bind = engine
                session.sync_session.bind = engine.sync_engine
