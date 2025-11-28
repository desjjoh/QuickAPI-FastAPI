from __future__ import annotations

import re
from typing import ClassVar

from fastapi import status
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.models.error_model import error_response


class HeaderSanitizationASGIMiddleware:

    BLOCKLIST: ClassVar[set[str]] = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "proxy-connection",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "forwarded",
        "via",
        "client-ip",
        "true-client-ip",
    }

    ALLOWLIST: ClassVar[set[str]] = {
        "host",
        "content-type",
        "content-length",
        "accept",
        "accept-language",
        "accept-encoding",
        "user-agent",
        "referer",
        "origin",
        "cookie",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-dest",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "authorization",
        "x-csrf-token",
        "x-request-id",
        "x-api-key",
    }

    VALID_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9-]+$")

    INVALID_VALUE_CHARS: ClassVar[set[str]] = {"\r", "\n"}

    def __init__(self, app: ASGIApp, extra_allowed: set[str] | None = None):
        self.app = app
        self.allowed = self.ALLOWLIST | (extra_allowed or set())

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)

            return

        path = scope.get("path", "")
        if path.startswith(
            (
                "/docs",
                "/redoc",
                "/openapi.json",
                "/favicon.ico",
            )
        ):
            await self.app(scope, receive, send)
            return

        raw_headers = scope.get("headers", [])
        cleaned_headers: list[tuple[bytes, bytes]] = []
        seen: set[str] = set()

        referer: str | None = None
        for k, v in raw_headers:
            if k.decode().lower() == "referer":
                referer = v.decode().lower()
                break

        if referer and "/docs" in referer:
            await self.app(scope, receive, send)
            return

        for raw_name, raw_value in raw_headers:
            name = raw_name.decode().lower()
            value = raw_value.decode()

            if name in self.BLOCKLIST:
                return await self._reject(
                    scope, send, f"Header '{name}' is not allowed."
                )

            if name in seen:
                return await self._reject(
                    scope, send, f"Duplicate header '{name}' is not permitted."
                )

            seen.add(name)

            if not self.VALID_NAME_RE.match(name):
                return await self._reject(
                    scope,
                    send,
                    f"Header name '{name}' contains invalid characters.",
                )

            if any(c in value for c in self.INVALID_VALUE_CHARS):
                return await self._reject(
                    scope,
                    send,
                    "Header value contains prohibited control characters.",
                )

            if name not in self.allowed:
                continue

            cleaned_headers.append((raw_name, raw_value))

        scope["headers"] = cleaned_headers

        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, send: Send, message: str):
        response: JSONResponse = error_response(
            status=status.HTTP_400_BAD_REQUEST,
            message=message,
        )

        async def empty_receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        await response(scope, empty_receive, send)
