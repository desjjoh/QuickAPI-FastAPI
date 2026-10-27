import pytest
from conftest import http_scope, invoke
from starlette.types import Receive, Scope, Send

from app.common.middleware.request_header_limit import (
    HeaderLimits,
    RequestHeaderLimitASGIMiddleware,
)
from app.common.middleware.request_header_sanitization import (
    HeaderSanitizationASGIMiddleware,
)
from app.common.middleware.trusted_proxy import TrustedProxyASGIMiddleware

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "peer,headers,expected_ip,expected_scheme,status",
    [
        (
            "10.0.0.1",
            [
                (b"x-forwarded-for", b"198.51.100.8, 10.0.0.2"),
                (b"x-forwarded-proto", b"https"),
            ],
            "198.51.100.8",
            "https",
            200,
        ),
        (
            "10.0.0.1",
            [(b"x-forwarded-for", b"192.0.2.99, 198.51.100.8")],
            "198.51.100.8",
            "http",
            200,
        ),
        (
            "10.0.0.1",
            [(b"x-forwarded-for", b"10.0.0.3, 10.0.0.2")],
            "10.0.0.3",
            "http",
            200,
        ),
        (
            "::1",
            [(b"x-forwarded-for", b"2001:db8::8, ::1")],
            "2001:db8::8",
            "http",
            200,
        ),
        ("10.0.0.1", [(b"x-forwarded-proto", b"https")], "10.0.0.1", "https", 200),
        ("10.0.0.1", [], "10.0.0.1", "http", 200),
        (
            "192.0.2.1",
            [(b"x-forwarded-for", b"198.51.100.8")],
            "192.0.2.1",
            "http",
            400,
        ),
        ("not-an-ip", [(b"x-forwarded-proto", b"https")], "not-an-ip", "http", 400),
        ("10.0.0.1", [(b"x-forwarded-for", b"unknown")], "10.0.0.1", "http", 400),
        (
            "10.0.0.1",
            [(b"x-forwarded-for", b"198.51.100.8,,10.0.0.2")],
            "10.0.0.1",
            "http",
            400,
        ),
        ("10.0.0.1", [(b"x-forwarded-for", b"fe80::1%eth0")], "10.0.0.1", "http", 400),
        (
            "10.0.0.1",
            [(b"x-forwarded-for", b"198.51.100.8"), (b"X-Forwarded-For", b"192.0.2.8")],
            "10.0.0.1",
            "http",
            400,
        ),
        ("10.0.0.1", [(b"x-forwarded-for", b"\xff")], "10.0.0.1", "http", 400),
        ("10.0.0.1", [(b"x-forwarded-proto", b"https\r\n")], "10.0.0.1", "http", 400),
        (
            "10.0.0.1",
            [(b"x-forwarded-for", b"198.51.100.8"), (b"x-forwarded-proto", b"ftp")],
            "10.0.0.1",
            "http",
            400,
        ),
        ("10.0.0.1", [(b"forwarded", b"for=198.51.100.8")], "10.0.0.1", "http", 400),
    ],
)
async def test_proxy_chain_and_invalid_forwarding(
    peer: str,
    headers: list[tuple[bytes, bytes]],
    expected_ip: str,
    expected_scheme: str,
    status: int,
) -> None:
    seen: list[Scope] = []

    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(dict(scope))
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b""})

    scope = http_scope(method="GET", client=(peer, 42), headers=headers)
    scope["scheme"] = "http"
    app = TrustedProxyASGIMiddleware(
        HeaderSanitizationASGIMiddleware(endpoint), ["10.0.0.0/8", "::1"]
    )
    sent = await invoke(app, scope)
    assert sent[0]["status"] == status
    assert scope["client"][0] == expected_ip
    assert scope["scheme"] == expected_scheme
    assert bool(seen) == (status == 200)
    if seen:
        assert not any(
            name.lower().startswith(b"x-forwarded-") for name, _ in seen[0]["headers"]
        )


@pytest.mark.parametrize(
    "headers,limits",
    [
        (
            [(b"x-forwarded-for", b"198.51.100.8"), (b"extra", b"value")],
            HeaderLimits(max_header_count=1),
        ),
        (
            [(b"x-forwarded-for", b"198.51.100.8")],
            HeaderLimits(max_single_header_bytes=20),
        ),
        (
            [(b"x-forwarded-for", b"198.51.100.8"), (b"extra", b"value")],
            HeaderLimits(max_total_header_bytes=30),
        ),
    ],
)
async def test_proxy_headers_cannot_escape_raw_header_budgets(
    headers: list[tuple[bytes, bytes]], limits: HeaderLimits
) -> None:
    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        pytest.fail("Over-budget forwarding must not reach the endpoint")

    scope = http_scope(headers, method="GET", client=("10.0.0.1", 42))
    app = TrustedProxyASGIMiddleware(
        RequestHeaderLimitASGIMiddleware(endpoint, limits),
        ["10.0.0.0/8"],
        max_header_bytes=limits.max_single_header_bytes,
        max_header_count=limits.max_header_count,
        max_total_header_bytes=limits.max_total_header_bytes,
    )
    sent = await invoke(app, scope)
    assert sent[0]["status"] == 431
    assert scope["client"] == ("10.0.0.1", 42)


async def test_non_http_and_missing_peer_are_unchanged() -> None:
    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "test.event"})

    app = TrustedProxyASGIMiddleware(endpoint, ["10.0.0.0/8"])
    scope: Scope = {
        "type": "websocket",
        "headers": [(b"x-forwarded-for", b"198.51.100.8")],
        "client": ("10.0.0.1", 42),
    }
    assert await invoke(app, scope) == [{"type": "test.event"}]
    assert scope["client"] == ("10.0.0.1", 42)
    no_peer: Scope = {"type": "http", "headers": []}
    assert await invoke(app, no_peer) == [{"type": "test.event"}]
