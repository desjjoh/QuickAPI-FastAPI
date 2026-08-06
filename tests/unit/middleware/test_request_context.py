from typing import cast
from unittest.mock import Mock

import pytest
from conftest import http_scope, invoke
from starlette.types import Receive, Scope, Send

from app.common.middleware.request_context import RequestContextASGIMiddleware
from app.common.store.request_context import RequestContext

pytestmark = pytest.mark.unit


async def test_context_scope_store_and_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str | None]] = []
    bind: Mock = Mock()
    monkeypatch.setattr(
        "app.common.middleware.request_context.structlog.contextvars.bind_contextvars",
        bind,
    )
    monkeypatch.setattr(
        "app.common.middleware.request_context.uuid.uuid4",
        lambda: Mock(hex="12345678rest"),
    )

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        scope_context = cast(dict[str, str], scope["ctx"])
        request_context = RequestContext.get()
        seen.append(
            (
                scope_context["request_id"],
                request_context.path if request_context is not None else None,
            )
        )
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body"})

    await invoke(RequestContextASGIMiddleware(app), http_scope(method="GET", path="/x"))
    assert seen[0] == ("12345678", "/x")
    bind.assert_called_once()
