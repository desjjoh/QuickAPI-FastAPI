from __future__ import annotations

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
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and (path == root or path.startswith(root + "/")):
            path = path[len(root) :]
        if path == "/favicon.ico" and scope["method"] in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return

        decision = self.limiter.admit(get_client_ip(Request(scope)))
        if not decision.allowed:
            seconds = f"{self.limiter.policy.window_ms / 1000:.3f}".rstrip("0").rstrip(
                "."
            )
            message = (
                "Rate limiter capacity is exhausted. Try again later."
                if decision.status == 503
                else f"Too many requests \u2014 limit is {self.limiter.policy.max_requests} per {seconds}s."
            )
            response = await http_exception_handler(
                Request(scope, receive),
                HTTPException(
                    decision.status or 429,
                    message,
                    headers={
                        "Retry-After": str(decision.retry_after_seconds),
                        "X-RateLimit-Result": "rejected",
                    },
                ),
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-ratelimit-result", b"accepted"))
            await send(message)

        await self.app(scope, receive, send_wrapper)
