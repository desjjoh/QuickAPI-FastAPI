import uuid

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

from app.store.request_context import RequestContext, RequestContextData


class RequestContextASGIMiddleware:

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_id = uuid.uuid4().hex[:8]
        method = scope["method"]
        path = scope["path"]
        client = scope.get("client", ["unknown"])[0]

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=method,
            path=path,
            ip=client,
        )

        scope["ctx"] = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "ip": client,
        }

        ctx = RequestContextData(
            request_id=request_id,
            method=method,
            path=path,
            ip=client,
        )

        RequestContext.set(ctx)

        try:
            await self.app(scope, receive, send)
        finally:
            structlog.contextvars.clear_contextvars()
