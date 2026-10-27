import asyncio
from unittest.mock import Mock

import pytest
from conftest import http_scope, invoke
from starlette.routing import Mount, Route, Router
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.middleware.request_outcome import (
    RequestObservation,
    RequestOutcome,
    RequestOutcomeASGIMiddleware,
    abort_request,
    observe_request,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "terminal",
    [
        "complete",
        "disconnect",
        "send_error",
        "receive_error",
        "cancel",
        "exception",
        "incomplete",
    ],
)
@pytest.mark.parametrize("headers", [False, True])
async def test_terminal_events_settle_once(terminal: str, headers: bool) -> None:
    results: list[RequestOutcome] = []
    scope = http_scope(method="GET")

    async def receive() -> Message:
        if terminal == "receive_error":
            raise OSError("closed")
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if terminal == "send_error" and message["type"] == "http.response.body":
            raise OSError("closed")

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        if headers or terminal == "complete":
            await send({"type": "http.response.start", "status": 200})
        if terminal in {"complete", "send_error"}:
            await send({"type": "http.response.body", "body": b"done"})
            if terminal == "complete":
                await receive()  # A post-completion disconnect must not recount.
        elif terminal in {"disconnect", "receive_error"}:
            await receive()
        elif terminal == "cancel":
            raise asyncio.CancelledError
        elif terminal == "exception":
            raise RuntimeError("broken")
        abort_request(scope)

    async def subscribed(scope: Scope, receive: Receive, send: Send) -> None:
        await observe_request(downstream, scope, receive, send, "test", results.append)

    wrapped = RequestOutcomeASGIMiddleware(subscribed)
    if terminal in {"send_error", "receive_error", "cancel", "exception"}:
        with pytest.raises((OSError, asyncio.CancelledError, RuntimeError)):
            await wrapped(scope, receive, send)
    else:
        await wrapped(scope, receive, send)
    assert len(results) == 1
    result = results[0]
    assert result.outcome == ("completed" if terminal == "complete" else "aborted")
    assert result.status == (200 if headers or terminal == "complete" else None)
    assert result.headers_sent == (result.status is not None)
    assert result.duration_ms >= 0


async def test_completion_precedes_cleanup_and_nested_subscribers_are_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Mock(return_value=1.0)
    monkeypatch.setattr(
        "app.common.middleware.request_outcome.time.perf_counter", clock
    )
    results: list[RequestOutcome] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        clock.return_value = 1.025
        await send({"type": "http.response.start", "status": 201})
        await send({"type": "http.response.body", "body": b""})
        assert len(results) == 1
        clock.return_value = 10.0
        abort_request(scope)
        raise RuntimeError("cleanup failed")

    async def subscriber(scope: Scope, receive: Receive, send: Send) -> None:
        await observe_request(app, scope, receive, send, "same", results.append)

    async def duplicate(scope: Scope, receive: Receive, send: Send) -> None:
        await observe_request(
            RequestOutcomeASGIMiddleware(subscriber),
            scope,
            receive,
            send,
            "same",
            results.append,
        )

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await invoke(RequestOutcomeASGIMiddleware(duplicate), http_scope())
    assert len(results) == 1
    assert results[0].duration_ms == pytest.approx(25)
    assert results[0].outcome == "completed"


def test_late_subscription_and_unsupported_method_are_bounded() -> None:
    observation = RequestObservation(http_scope(method="CUSTOM-PRIVATE-VALUE"), ())
    observation.settle("aborted")
    callback = Mock()
    observation.subscribe("late", callback)
    observation.subscribe("late", callback)
    callback.assert_called_once_with(observation.result)
    assert observation.result is not None
    assert observation.result.method == "<other>"
    assert observation.result.route == "<unmatched>"
    abort_request(http_scope())


@pytest.mark.parametrize("channel", ["receive", "send"])
async def test_transport_timeout_is_not_treated_as_disconnect(channel: str) -> None:
    results: list[RequestOutcome] = []

    async def receive() -> Message:
        raise TimeoutError

    async def send(message: Message) -> None:
        raise TimeoutError

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            if channel == "receive":
                await receive()
            else:
                await send({"type": "http.response.start", "status": 200})
        except TimeoutError:
            assert not results  # No inferred disconnect while work can still recover.

    async def subscribed(scope: Scope, receive: Receive, send: Send) -> None:
        await observe_request(app, scope, receive, send, "test", results.append)

    await RequestOutcomeASGIMiddleware(subscribed)(http_scope(), receive, send)
    assert len(results) == 1 and results[0].status is None


async def test_non_http_is_passed_through(app: ASGIApp) -> None:
    callback = Mock()
    scope: Scope = {"type": "websocket"}

    async def subscribed(scope: Scope, receive: Receive, send: Send) -> None:
        await observe_request(app, scope, receive, send, "test", callback)

    await invoke(RequestOutcomeASGIMiddleware(subscribed), scope)
    callback.assert_not_called()


@pytest.mark.parametrize(
    "path,method,expected",
    [
        ("/teams/secret/entries/123", "GET", "/teams/{team}/entries/{id}"),
        ("/alternate/entries/999", "GET", "/alternate/entries/{id}"),
        ("/teams/secret/entries/123", "DELETE", "/teams/{team}/entries/{id}"),
        ("/teams/secret/missing/private", "GET", "<unmatched>"),
        ("/opaque/private", "GET", "<unmatched>"),
    ],
)
async def test_declared_mount_templates_and_405(
    path: str, method: str, expected: str
) -> None:
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    async def endpoint(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def opaque(scope: Scope, receive: Receive, send: Send) -> None:
        await PlainTextResponse("ok")(scope, receive, send)

    child = Router(routes=[Route("/entries/{id}", endpoint)])
    routes = [
        Mount("/teams/{team}", child),
        Mount("/alternate", child),
        Mount("/opaque", opaque),
    ]
    router = Router(routes=routes)
    results: list[RequestOutcome] = []

    async def subscribed(scope: Scope, receive: Receive, send: Send) -> None:
        await observe_request(router, scope, receive, send, "test", results.append)

    await invoke(
        RequestOutcomeASGIMiddleware(subscribed, routes),
        http_scope(method=method, path=path),
    )
    assert len(results) == 1
    assert results[0].route == expected
