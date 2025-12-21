from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import status
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


async def empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def format_bytes_as_mb(value: int) -> str:
    mb: float = value / (1024 * 1024)

    return f"{mb:.2f} MB"


def format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"

    kb = value / 1024
    if kb < 1024:
        return f"{kb:.2f} KB"

    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.2f} MB"

    gb = mb / 1024
    return f"{gb:.2f} GB"


@dataclass(frozen=True)
class BodyLimit:
    max_body_bytes: int = 1_048_576


class RequestBodyLimitASGIMiddleware:

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: BodyLimit,
        route_overrides: Sequence[tuple[str, BodyLimit]] | None = None,
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.route_overrides = route_overrides or []

    def _select_limit(self, path: str) -> BodyLimit:
        for prefix, override in self.route_overrides:
            if path.startswith(prefix):
                return override
        return self.default_limit

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self._run(scope, receive, send)

        except HTTPException as exc:
            request = Request(scope, receive=receive)
            response = await http_exception_handler(request, exc)
            await response(scope, empty_receive, send)

    async def _run(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:

        path: str = scope.get("path", "/")
        limit: BodyLimit = self._select_limit(path)
        max_bytes: int = limit.max_body_bytes

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        content_length = headers.get("content-length")

        if content_length is not None:
            try:
                declared: int = int(content_length)

            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Invalid Content-Length header.",
                )
            if declared > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        f"Request body exceeds maximum allowed size "
                        f"(limit = {format_bytes(max_bytes)})."
                    ),
                )

        total: int = 0
        body_chunks: list[bytes] = []

        async def limited_receive() -> Message:
            nonlocal total

            message: Message = await receive()

            if message["type"] == "http.request":
                chunk = message.get("body", b"") or b""
                chunk_len: int = len(chunk)

                if chunk_len:
                    total += chunk_len

                    if total > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                f"Request body exceeds maximum allowed size "
                                f"(limit = {format_bytes(max_bytes)})."
                            ),
                        )

                    body_chunks.append(chunk)

            return message

        async def replay_body() -> Message:
            nonlocal body_chunks

            if body_chunks:
                merged: bytes = b"".join(body_chunks)
                body_chunks = []

                return {"type": "http.request", "body": merged, "more_body": False}
            return await empty_receive()

        scope["_body_replay"] = replay_body

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                remaining: int = max(max_bytes - total, 0)
                hdrs = list(message.get("headers", []))

                hdrs.append((b"x-body-limit-bytes", str(max_bytes).encode()))
                hdrs.append((b"x-body-remaining-bytes", str(remaining).encode()))

                message["headers"] = hdrs

            await send(message)

        await self.app(scope, limited_receive, send_wrapper)
