"""Opt-in transaction ownership around FastAPI's normal response preparation."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import event

from app.common.handlers.request_activity import request_activity
from app.config import database

TRANSACTION_SESSION_KEY = database.TRANSACTION_SESSION_KEY
_MARKER = '__quickapi_transactional__'


def transactional[Endpoint: Callable[..., Any]](endpoint: Endpoint) -> Endpoint:
    """Mark an ApplicationRoute endpoint without replacing its signature."""
    setattr(endpoint, _MARKER, True)
    return endpoint


class ApplicationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        prepare = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if not getattr(self.endpoint, _MARKER, False):
                return await prepare(request)
            if TRANSACTION_SESSION_KEY in request.scope:
                raise RuntimeError('A mutation transaction already owns this request.')
            activity = request_activity(request.scope)
            activity.assert_active()
            activity.owns_mutation = True
            # Explicit begin is required, including for any attempted use after
            # commit. A borrowed session cannot silently start a second transaction.
            async with database.SessionLocal(autobegin=False) as session:
                if session.in_transaction():
                    raise RuntimeError('A mutation requires a fresh transaction owner.')
                request.scope[TRANSACTION_SESSION_KEY] = session

                # Session.begin() is logical: actual checkout/connect can happen
                # later. Guard after acquisition and BEGIN, before business SQL.
                def acquired(*_: object) -> None:
                    activity.assert_active()

                event.listen(session.sync_session, 'after_begin', acquired)
                try:
                    async with session.begin():
                        activity.assert_active()
                        response = await prepare(request)
                        if (
                            not isinstance(response, JSONResponse)
                            or response.background is not None
                        ):
                            raise RuntimeError(
                                'Transactional routes require buffered JSON without background tasks.'
                            )
                        if response.status_code >= 400:
                            await session.rollback()
                        else:
                            await session.flush()
                            # Check the clock, not just the timer callback: work
                            # may have delayed the loop or caught cancellation.
                            activity.assert_active()
                    return response
                finally:
                    event.remove(session.sync_session, 'after_begin', acquired)
                    request.scope.pop(TRANSACTION_SESSION_KEY, None)

        return handle
