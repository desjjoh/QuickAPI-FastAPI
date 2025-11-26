from __future__ import annotations

from datetime import UTC, datetime

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RequestSizeLimitASGIMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = 1_048_576):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        content_length = headers.get("content-length")

        if content_length is not None:
            try:
                declared_len: int = int(content_length)

            except ValueError:
                return await self._reject(scope, receive, send)

            if declared_len > self.max_body_bytes:
                return await self._reject(scope, receive, send)

        actual_received: int = 0

        async def limited_receive():
            nonlocal actual_received
            message: Message = await receive()

            if message["type"] == "http.request":
                body_chunk = message.get("body", b"")
                actual_received += len(body_chunk)

                if actual_received > self.max_body_bytes:
                    return {"type": "http.disconnect"}

            return message

        await self.app(scope, limited_receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send):
        response: JSONResponse = JSONResponse(
            status_code=413,
            content={
                "status": 413,
                "message": "Request body exceeds maximum allowed size (1MB).",
                "timestamp": _now(),
            },
        )
        await response(scope, receive, send)
