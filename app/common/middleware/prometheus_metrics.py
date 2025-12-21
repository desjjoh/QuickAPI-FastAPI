from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config.metrics import REQUEST_COUNT, REQUEST_LATENCY


class PrometheusASGIMiddleware:

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method: str = scope["method"]
        path: str = scope.get("path", "")

        start: float = time.perf_counter()
        status_code_holder: dict[str, str] = {"status": "0"}

        async def send_wrapper(message: Message):
            if message["type"] == "http.response.start":
                status_code_holder["status"] = str(message["status"])

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)

        finally:
            latency: float = time.perf_counter() - start

            REQUEST_LATENCY.labels(method, path).observe(latency)
            REQUEST_COUNT.labels(method, path, status_code_holder["status"]).inc()
