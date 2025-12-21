from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler
from app.config.rate_limiter import RateLimiter


def get_client_ip(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


class RateLimitASGIMiddleware:

    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self._run_rate_limit(scope, receive, send)

        except HTTPException as exc:
            request: Request = Request(scope, receive=receive)
            response: JSONResponse = await http_exception_handler(request, exc)

            async def empty_receive() -> Message:
                return {"type": "http.request", "body": b"", "more_body": False}

            return await response(scope, empty_receive, send)

    async def _run_rate_limit(self, scope: Scope, receive: Receive, send: Send) -> None:
        request: Request = Request(scope)
        ip: str = get_client_ip(request)

        allowed: bool = self.limiter.allow(ip)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please slow down.",
            )

        await self.app(scope, receive, send)
