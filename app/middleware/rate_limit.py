from __future__ import annotations

from fastapi import status
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.rate_limiter import RateLimiter
from app.models.error_model import error_response


def get_client_ip(request: Request) -> str:
    client = request.client

    if client is None:
        return "unknown"

    return client.host


class RateLimitASGIMiddleware:
    def __init__(self, app: ASGIApp, limiter: RateLimiter):
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)

            return

        request: Request = Request(scope)
        ip: str = get_client_ip(request)
        allowed: bool = self.limiter.allow(ip)

        if not allowed:
            response: JSONResponse = error_response(
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                message="Too many requests — please slow down.",
            )

            await response(scope, receive, send)

            return

        await self.app(scope, receive, send)
