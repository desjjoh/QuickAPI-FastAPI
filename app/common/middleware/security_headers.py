from __future__ import annotations

from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

        self.headers: Iterable[tuple[bytes, bytes]] = [
            (b"x-frame-options", b"DENY"),
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"x-xss-protection", b"0"),
            (
                b"strict-transport-security",
                b"max-age=63072000; includeSubDomains; preload",
            ),
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-embedder-policy", b"require-corp"),
            (b"cross-origin-resource-policy", b"same-origin"),
            (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
            (
                b"content-security-policy",
                b"default-src 'self'; "
                b"img-src 'self' data:; "
                b"object-src 'none'; "
                b"frame-ancestors 'none'; "
                b"base-uri 'self'",
            ),
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if path.startswith(("/docs", "/redoc", "/openapi.json")):
            return await self.app(scope, receive, send)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = message.setdefault("headers", [])

                for key, value in self.headers:
                    raw_headers.append((key, value))

            await send(message)

        await self.app(scope, receive, send_wrapper)
