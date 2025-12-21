from __future__ import annotations

from collections.abc import Iterable

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


class CustomCORSASGIMiddleware:

    def __init__(
        self,
        app: ASGIApp,
        *,
        origin: str | list[str],
        methods: Iterable[str],
        allowed_headers: Iterable[str],
        exposed_headers: Iterable[str],
        credentials: bool = False,
        max_age: int = 86400,
    ) -> None:
        self.app = app
        self.opts_origin = origin
        self.opts_methods = {m.upper() for m in methods}
        self.opts_allowed_headers = list(allowed_headers)
        self.opts_exposed_headers = list(exposed_headers)
        self.credentials = credentials
        self.max_age = max_age

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self._run_cors_logic(scope, receive, send)
        except HTTPException as exc:
            request: Request = Request(scope, receive=receive)
            response: JSONResponse = await http_exception_handler(request, exc)

            async def empty_receive() -> Message:
                return {"type": "http.request", "body": b"", "more_body": False}

            await response(scope, empty_receive, send)

    async def _run_cors_logic(self, scope: Scope, receive: Receive, send: Send) -> None:
        method = scope["method"].upper()
        headers: dict[str, str] = self._extract_headers(scope)
        origin: str | None = headers.get("origin")

        if not self._is_allowed_origin(origin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"CORS origin '{origin}' not allowed.",
            )

        if method == "OPTIONS":
            return await self._respond_preflight(origin, scope, send)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers_list: list[tuple[bytes, bytes]] = message.setdefault(
                    "headers", []
                )

                self._append_header(
                    headers_list, "access-control-allow-origin", origin or "*"
                )
                self._append_header(
                    headers_list,
                    "access-control-allow-methods",
                    ", ".join(self.opts_methods),
                )
                self._append_header(
                    headers_list,
                    "access-control-allow-headers",
                    ", ".join(self.opts_allowed_headers),
                )
                self._append_header(
                    headers_list,
                    "access-control-expose-headers",
                    ", ".join(self.opts_exposed_headers),
                )
                self._append_header(
                    headers_list, "access-control-max-age", str(self.max_age)
                )

                if self.credentials:
                    self._append_header(
                        headers_list, "access-control-allow-credentials", "true"
                    )

            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    def _extract_headers(scope: Scope) -> dict[str, str]:
        return {
            key.decode().lower(): value.decode()
            for key, value in scope.get("headers", [])
        }

    def _is_allowed_origin(self, origin: str | None) -> bool:
        if not origin:
            return True

        opts: str | list[str] = self.opts_origin

        if opts == "*" or (isinstance(opts, list) and "*" in opts):
            return True

        if isinstance(opts, list):
            return origin in opts

        return opts == origin

    @staticmethod
    def _append_header(
        headers_list: list[tuple[bytes, bytes]], key: str, value: str
    ) -> None:
        headers_list.append((key.encode(), value.encode()))

    async def _respond_preflight(
        self, origin: str | None, scope: Scope, send: Send
    ) -> None:
        from starlette.responses import Response

        headers: dict[str, str] = {
            "Access-Control-Allow-Origin": origin or "*",
            "Access-Control-Allow-Methods": ", ".join(self.opts_methods),
            "Access-Control-Allow-Headers": ", ".join(self.opts_allowed_headers),
            "Access-Control-Max-Age": str(self.max_age),
        }

        if self.credentials:
            headers["Access-Control-Allow-Credentials"] = "true"

        response: Response = Response(status_code=204, headers=headers)

        async def empty_receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        await response(scope, empty_receive, send)
