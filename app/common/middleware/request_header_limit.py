from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


async def empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


@dataclass(frozen=True)
class HeaderLimits:
    max_header_count: int = 100
    max_single_header_bytes: int = 4_096
    max_total_header_bytes: int = 8_192
    allow_chunked: bool = False


class RequestHeaderLimitASGIMiddleware:
    def __init__(self, app: ASGIApp, limits: HeaderLimits = HeaderLimits()) -> None:
        self.app = app
        self.limits = limits

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

        if len(raw_headers) > self.limits.max_header_count:
            raise HTTPException(
                status_code=status.HTTP_431_REQUEST_HEADER_FIELDS_TOO_LARGE,
                detail=f"Too many headers (limit = {self.limits.max_header_count}).",
            )

        total_bytes: int = 0

        for key, value in raw_headers:
            size = len(key) + len(value)
            total_bytes += size

            if size > self.limits.max_single_header_bytes:
                raise HTTPException(
                    status_code=status.HTTP_431_REQUEST_HEADER_FIELDS_TOO_LARGE,
                    detail=(
                        f"Header exceeds per-header size limit "
                        f"({self.limits.max_single_header_bytes} bytes)."
                    ),
                )

        if total_bytes > self.limits.max_total_header_bytes:
            raise HTTPException(
                status_code=status.HTTP_431_REQUEST_HEADER_FIELDS_TOO_LARGE,
                detail=(
                    f"Total header size exceeds limit "
                    f"({self.limits.max_total_header_bytes} bytes)."
                ),
            )

        headers_map = {k.decode().lower(): v.decode() for k, v in raw_headers}
        transfer = headers_map.get("transfer-encoding")

        if not self.limits.allow_chunked and transfer:
            if "chunked" in transfer.lower():
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="Chunked request bodies are not allowed.",
                )

        await self.app(scope, receive, send)
