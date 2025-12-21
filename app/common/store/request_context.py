from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestContextData:
    request_id: str
    method: str
    path: str
    ip: str


_request_context: ContextVar[RequestContextData | None] = ContextVar(
    "request_context", default=None
)


class RequestContext:
    @staticmethod
    def get() -> RequestContextData | None:
        return _request_context.get()

    @staticmethod
    def set(ctx: RequestContextData) -> None:
        _request_context.set(ctx)

    @staticmethod
    def clear() -> None:
        _request_context.set(None)
