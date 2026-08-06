from typing import cast

import pytest
from conftest import http_scope, invoke
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.middleware.request_body_limit import (
    BodyLimit,
    RequestBodyLimitASGIMiddleware,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value,status", [(None, 200), (b"4", 200), (b"no", 413), (b"-1", 413), (b"5", 413)]
)
async def test_content_length_cases(
    app: ASGIApp, value: bytes | None, status: int
) -> None:
    headers: list[tuple[bytes, bytes]] = (
        [] if value is None else [(b"content-length", value)]
    )
    response = await invoke(
        RequestBodyLimitASGIMiddleware(app, default_limit=BodyLimit(4)),
        http_scope(headers),
        [{"type": "http.request", "body": b"1234"}],
    )
    assert response[0]["status"] == status


async def test_exact_and_oversized_streams_and_replay() -> None:
    replayed: list[bytes] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await receive()
        replay = cast(Receive, scope["_body_replay"])
        replayed.extend([(await replay())["body"], (await replay())["body"]])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body"})

    chunks: list[Message] = [
        {"type": "http.request", "body": b"12", "more_body": True},
        {"type": "http.request", "body": b"34", "more_body": False},
    ]
    sent = await invoke(
        RequestBodyLimitASGIMiddleware(downstream, default_limit=BodyLimit(4)),
        http_scope(),
        chunks,
    )
    assert sent[0]["status"] == 200 and replayed == [b"1234", b""]
    sent = await invoke(
        RequestBodyLimitASGIMiddleware(downstream, default_limit=BodyLimit(3)),
        http_scope(),
        chunks,
    )
    assert sent[0]["status"] == 413


async def test_non_http_bypass(app: ASGIApp) -> None:
    sent = await invoke(
        RequestBodyLimitASGIMiddleware(app, default_limit=BodyLimit(1)),
        {"type": "websocket", "path": "/"},
    )
    assert sent[0]["status"] == 200
