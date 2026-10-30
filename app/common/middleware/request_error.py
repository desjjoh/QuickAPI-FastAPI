"""Render application failures before response policy wrappers unwind."""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import unhandled_exception_handler


class RequestErrorASGIMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)

            return

        started = False

        async def send_tracked(message: Message) -> None:
            nonlocal started

            if message['type'] == 'http.response.start':
                started = True

            await send(message)

        try:
            await self.app(scope, receive, send_tracked)
        except Exception as exc:
            if started:
                # Preserve the server's incomplete-response/connection-close path.
                # The outer server-error handler logs this failure once.
                raise

            response = await unhandled_exception_handler(Request(scope), exc)

            await response(scope, receive, send)
