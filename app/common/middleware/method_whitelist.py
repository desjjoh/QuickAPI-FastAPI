from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


class MethodWhitelistASGIMiddleware:

    def __init__(self, app: ASGIApp, allowed_methods: set[str]) -> None:
        self.app = app
        self.allowed_methods = {m.upper() for m in allowed_methods}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self._run_method_check(scope, receive, send)

        except HTTPException as exc:
            request: Request = Request(scope, receive=receive)
            response: JSONResponse = await http_exception_handler(request, exc)

            async def empty_receive() -> Message:
                return {"type": "http.request", "body": b"", "more_body": False}

            return await response(scope, empty_receive, send)

    async def _run_method_check(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        method = scope.get("method", "").upper()

        if method not in self.allowed_methods:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail=f"HTTP method '{method}' is not allowed on this server.",
            )

        await self.app(scope, receive, send)
