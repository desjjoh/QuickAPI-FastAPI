from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.logging import log


class ErrorLoggingASGIMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        try:
            await self.app(scope, receive, send)

        except Exception as exc:
            log.error(f"{exc}")

            raise
