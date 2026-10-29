"""Opt-in transaction ownership around FastAPI's normal response preparation."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

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
            # Explicit begin is required, including for any attempted use after
            # commit. A borrowed session cannot silently start a second transaction.
            async with database.SessionLocal(autobegin=False) as session:
                if session.in_transaction():
                    raise RuntimeError('A mutation requires a fresh transaction owner.')
                request.scope[TRANSACTION_SESSION_KEY] = session
                try:
                    async with session.begin():
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
                    return response
                finally:
                    request.scope.pop(TRANSACTION_SESSION_KEY, None)

        return handle
