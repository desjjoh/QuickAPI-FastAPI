from starlette.types import ASGIApp, Receive, Scope, Send

from app.common.middleware.request_outcome import RequestOutcome, observe_request
from app.config.metrics import REQUEST_ABORTED, REQUEST_COUNT, REQUEST_DURATION


class PrometheusASGIMiddleware:
    # Operational polling is intentionally omitted from application traffic metrics.
    _excluded_paths: frozenset[str] = frozenset(
        {"/health", "/ready", "/info", "/system", "/metrics"}
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("path") in self._excluded_paths:
            await self.app(scope, receive, send)

            return

        def record(result: RequestOutcome) -> None:
            if result.outcome == "aborted":
                REQUEST_ABORTED.labels(result.method, result.route).inc()

                return

            status = str(result.status)

            REQUEST_COUNT.labels(result.method, result.route, status).inc()
            REQUEST_DURATION.labels(result.method, result.route, status).observe(
                result.duration_ms
            )

        await observe_request(self.app, scope, receive, send, "metrics", record)
