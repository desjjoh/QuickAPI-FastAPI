from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


class ContentTypeEnforcementASGIMiddleware:

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_allowed: set[str] | None = None,
        route_overrides: list[tuple[str, set[str]]] | None = None,
    ) -> None:
        self.app = app
        self.default_allowed = default_allowed or {"application/json"}
        self.route_overrides = route_overrides or []

        self.no_body_methods = {"GET", "DELETE", "HEAD", "OPTIONS"}

    def _allowed_for_path(self, path: str) -> set[str]:
        for prefix, allowed in self.route_overrides:
            if path.startswith(prefix):
                return allowed

        return self.default_allowed

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self._run_content_type_logic(scope, receive, send)

        except HTTPException as exc:
            request: Request = Request(scope, receive=receive)
            response: JSONResponse = await http_exception_handler(request, exc)

            async def empty_receive() -> Message:
                return {"type": "http.request", "body": b"", "more_body": False}

            return await response(scope, empty_receive, send)

    async def _run_content_type_logic(self, scope: Scope, receive: Receive, send: Send):
        method: str = scope.get("method", "").upper()
        path: str = scope.get("path", "")
        raw_headers = scope.get("headers", [])

        header_map = {k.decode().lower(): v.decode() for k, v in raw_headers}
        content_type = header_map.get("content-type")

        if method in self.no_body_methods:
            if content_type is not None:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"HTTP method '{method}' does not accept a request body.",
                )

            return await self.app(scope, receive, send)

        if method in {"POST", "PUT", "PATCH"}:
            allowed: set[str] = self._allowed_for_path(path)

            if content_type is None:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Missing Content-Type header.",
                )

            normalized = content_type.split(";")[0].strip().lower()

            if normalized not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=(
                        f"Content-Type '{content_type}' is not allowed on this endpoint. "
                        f"Expected one of: {sorted(allowed)}."
                    ),
                )

        await self.app(scope, receive, send)
