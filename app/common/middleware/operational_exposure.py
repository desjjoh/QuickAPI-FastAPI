"""Reserve disabled operational route families before any handler can execute."""

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.common.handlers.exception_handler import http_exception_handler


class OperationalExposureASGIMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        docs_enabled: bool,
        diagnostics_enabled: bool,
        metrics_enabled: bool,
    ) -> None:
        self.app = app
        self.disabled = tuple(
            path
            for enabled, paths in (
                (docs_enabled, ("/docs", "/redoc", "/openapi.json")),
                (diagnostics_enabled, ("/info", "/system")),
                (metrics_enabled, ("/metrics",)),
            )
            if not enabled
            for path in paths
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            root = scope.get("root_path", "")
            if root and (path == root or path.startswith(root + "/")):
                path = path[len(root) :]
            path = path.lower()
            if any(
                path == prefix or path.startswith(prefix + "/")
                for prefix in self.disabled
            ):
                response = await http_exception_handler(
                    Request(scope, receive), HTTPException(404, "Not Found")
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
