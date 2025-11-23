# app/middleware/request_logger.py
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config.logging import log


def shorten_path(path: str, max_len: int = 30) -> str:
    if len(path) > max_len:
        return path[: max_len - 1] + "…"

    return path


class RequestLoggingASGIMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):

        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        start = time.perf_counter()

        method = scope.get("method", "-")
        path = scope.get("path", "-")

        status: int | None = None

        async def send_wrapper(message: Message):
            nonlocal status

            if message["type"] == "http.response.start":
                status = message["status"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)

        finally:
            duration = (time.perf_counter() - start) * 1000
            duration_s = f"{duration:.2f}ms"

            status_code = status if status is not None else 500

            status_padded = str(status_code).ljust(3)
            method_padded = method.ljust(7)
            path_padded = shorten_path(path, 30).ljust(32)

            msg = f"{status_padded} {method_padded} {path_padded} {duration_s}"

            level = (
                "error"
                if status_code >= 500
                else "warning" if status_code >= 400 else "debug"
            )

            getattr(log, level)(msg)
