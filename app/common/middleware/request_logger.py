from typing import Literal

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

from app.common.middleware.request_outcome import RequestOutcome, observe_request
from app.common.store.request_context import RequestContext
from app.config.logging import log


def shorten_path(path: str, max_len: int = 30) -> str:
    if len(path) > max_len:
        return path[: max_len - 1] + "…"

    return path


class RequestLoggingASGIMiddleware:

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        context = RequestContext.get()
        request_id = context.request_id if context is not None else None

        def record(result: RequestOutcome) -> None:
            status = result.status
            status_label = str(status) if result.outcome == "completed" else "ABORTED"
            msg = (
                f"{status_label.ljust(3)} {result.method.ljust(7)} "
                f"{shorten_path(result.route, 30).ljust(32)} {result.duration_ms:.2f}ms"
            )
            level: Literal["error", "warning", "debug"] = (
                "error"
                if status is not None and status >= 500
                else (
                    "warning"
                    if result.outcome == "aborted"
                    or (status is not None and status >= 400)
                    else "debug"
                )
            )
            # The final server error can be emitted after request context cleanup.
            with structlog.contextvars.bound_contextvars(request_id=request_id):
                getattr(log, level)(
                    msg,
                    requestId=request_id,
                    method=result.method,
                    route=result.route,
                    status=result.status,
                    durationMs=result.duration_ms,
                    outcome=result.outcome,
                    headersSent=result.headers_sent,
                )

        await observe_request(self.app, scope, receive, send, "logging", record)
