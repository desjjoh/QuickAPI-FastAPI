from __future__ import annotations

import re
from typing import ClassVar

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


async def empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class HeaderSanitizationASGIMiddleware:

    BLOCKLIST: ClassVar[set[str]] = {
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
        "connection",
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

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self._run(scope, receive, send)

        except HTTPException as exc:
            request: Request = Request(scope, receive=receive)
            response: JSONResponse = await http_exception_handler(request, exc)

            await response(scope, empty_receive, send)

    async def _run(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        raw_headers = scope.get("headers", [])
        cleaned_headers: list[tuple[bytes, bytes]] = []
        seen: set[str] = set()

        for raw_name, raw_value in raw_headers:
            name = raw_name.decode().lower()
            value = raw_value.decode()

            if name in self.BLOCKLIST:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Header '{name}' is not allowed.",
                )

            if name in seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Duplicate header '{name}' is not permitted.",
                )

            seen.add(name)

            if not self.VALID_NAME_RE.match(name):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Header name '{name}' contains invalid characters.",
                )

            if any(c in value for c in self.INVALID_VALUE_CHARS):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Header value contains prohibited control characters.",
                )

            if name not in self.allowed:
                continue

            cleaned_headers.append((raw_name, raw_value))

        scope["headers"] = cleaned_headers

        await self.app(scope, receive, send)
