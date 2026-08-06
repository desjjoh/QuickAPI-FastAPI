from unittest.mock import Mock

import pytest
from conftest import http_scope, invoke
from starlette.types import Receive, Scope, Send

from app.common.middleware.request_cleanup import RequestCleanupASGIMiddleware
from app.common.store.request_context import RequestContext, RequestContextData

pytestmark = pytest.mark.unit


async def test_cleanup_after_success_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear = Mock()
    monkeypatch.setattr(
        "app.common.middleware.request_cleanup.structlog.contextvars.clear_contextvars",
        clear,
    )
    for raises in [False, True]:
        RequestContext.set(RequestContextData("id", "GET", "/", "ip"))

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if raises:
                raise RuntimeError
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body"})

        if raises:
            with pytest.raises(RuntimeError):
                await invoke(RequestCleanupASGIMiddleware(app), http_scope())
        else:
            await invoke(RequestCleanupASGIMiddleware(app), http_scope())
        assert RequestContext.get() is None
    assert clear.call_count == 2
