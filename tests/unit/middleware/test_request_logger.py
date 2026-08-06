from unittest.mock import Mock

import pytest
from conftest import http_scope, invoke
from starlette.types import ASGIApp, Receive, Scope, Send

from app.common.middleware.request_logger import (
    RequestLoggingASGIMiddleware,
    shorten_path,
)

pytestmark = pytest.mark.unit


async def test_emitted_level_and_fields(
    app: ASGIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    logger = Mock()
    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)
    monkeypatch.setattr(
        "app.common.middleware.request_logger.time.perf_counter",
        Mock(side_effect=[1, 1.01]),
    )
    await invoke(
        RequestLoggingASGIMiddleware(app), http_scope(method="GET", path="/hello")
    )
    message = logger.info.call_args.args[0]
    assert (
        "200" in message
        and "GET" in message
        and "/hello" in message
        and "10.00ms" in message
    )


async def test_exception_logs_error(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = Mock()
    monkeypatch.setattr("app.common.middleware.request_logger.log", logger)

    async def broken(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError

    with pytest.raises(RuntimeError):
        await invoke(RequestLoggingASGIMiddleware(broken), http_scope())
    logger.error.assert_called_once()
    assert shorten_path("x" * 40).endswith("…")
