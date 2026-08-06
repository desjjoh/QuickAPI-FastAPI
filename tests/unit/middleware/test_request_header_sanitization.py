from typing import cast

import pytest
from conftest import http_scope, invoke
from starlette.types import Receive, Scope, Send

from app.common.middleware.request_header_sanitization import (
    HeaderSanitizationASGIMiddleware,
)

pytestmark = pytest.mark.unit


async def capture(
    headers: list[tuple[bytes, bytes]], extra: set[str] | None = None
) -> tuple[int, list[tuple[bytes, bytes]]]:
    seen: list[tuple[bytes, bytes]] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.extend(cast(list[tuple[bytes, bytes]], scope["headers"]))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body"})

    sent = await invoke(
        HeaderSanitizationASGIMiddleware(app, extra), http_scope(headers)
    )
    return cast(int, sent[0]["status"]), seen


async def test_casing_allowed_custom_and_unknown_filtering() -> None:
    status, headers = await capture(
        [(b"X-CUSTOM", b"safe"), (b"x-unknown", b"drop")], {"x-custom"}
    )
    assert status == 200 and headers == [(b"X-CUSTOM", b"safe")]


@pytest.mark.parametrize(
    "headers",
    [
        [(b"x-forwarded-for", b"1")],
        [(b"host", b"a"), (b"HOST", b"b")],
        [(b"bad name", b"x")],
        [(b"host", b"a\r\nb")],
    ],
)
async def test_forbidden_duplicate_and_malformed(
    headers: list[tuple[bytes, bytes]],
) -> None:
    assert (await capture(headers))[0] == 400


async def test_non_ascii_rejected_not_crash() -> None:
    assert (await capture([(b"host", b"\xff")]))[0] == 400
