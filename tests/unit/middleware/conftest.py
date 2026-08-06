from collections.abc import Mapping
from typing import Protocol

import httpx
import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

pytestmark = pytest.mark.unit


class RequestCall(Protocol):
    async def __call__(
        self,
        app: ASGIApp,
        method: str = "GET",
        path: str = "/",
        *,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response: ...


async def ok_app(scope: Scope, receive: Receive, send: Send) -> None:
    body = b""
    if scope["type"] == "http":
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
    await send(
        {"type": f"{scope['type']}.response.start", "status": 200, "headers": []}
    )
    await send({"type": f"{scope['type']}.response.body", "body": body})


@pytest.fixture
def app() -> ASGIApp:
    return ok_app


@pytest.fixture
def call() -> RequestCall:
    async def request(
        app: ASGIApp,
        method: str = "GET",
        path: str = "/",
        *,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.request(method, path, content=content, headers=headers)

    return request


async def invoke(
    app: ASGIApp, scope: Scope, messages: list[Message] | None = None
) -> list[Message]:
    default_messages: list[Message] = [{"type": "http.request", "body": b""}]
    incoming = iter(messages if messages is not None else default_messages)
    sent: list[Message] = []

    async def receive() -> Message:
        return next(incoming)

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def http_scope(
    headers: list[tuple[bytes, bytes]] | None = None,
    *,
    method: str = "POST",
    path: str = "/",
    client: tuple[str, int] = ("1.2.3.4", 1),
) -> Scope:
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "client": client,
    }
    return scope
