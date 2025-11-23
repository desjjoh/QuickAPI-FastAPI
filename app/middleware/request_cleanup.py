import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

from app.store.request_context import RequestContext


class RequestCleanupASGIMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        try:
            await self.app(scope, receive, send)

        finally:
            structlog.contextvars.clear_contextvars()
            RequestContext.clear()
