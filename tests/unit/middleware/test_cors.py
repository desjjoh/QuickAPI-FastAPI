import pytest
from conftest import http_scope, invoke
from starlette.types import ASGIApp, Message

from app.common.middleware.cors import CustomCORSASGIMiddleware

pytestmark = pytest.mark.unit


def cors(
    app: ASGIApp,
    *,
    origin: str | list[str] | None = None,
    credentials: bool = True,
) -> CustomCORSASGIMiddleware:
    return CustomCORSASGIMiddleware(
        app,
        origin=origin if origin is not None else ["https://ok"],
        methods=["GET", "POST"],
        allowed_headers=["content-type", "x-ok"],
        exposed_headers=["x-result"],
        credentials=credentials,
    )


async def req(
    app: ASGIApp,
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> list[Message]:
    return await invoke(
        cors(app),
        http_scope(headers or [], method=method),
        [{"type": "http.request", "body": b""}],
    )


def headers(sent: list[Message]) -> dict[str, str]:
    raw_headers = sent[0].get("headers", [])
    return {key.decode(): value.decode() for key, value in raw_headers}


async def test_simple_origin_credentials_exposed_and_vary(app: ASGIApp) -> None:
    h = headers(await req(app, headers=[(b"origin", b"https://ok")]))
    assert (
        h["access-control-allow-origin"] == "https://ok"
        and h["access-control-allow-credentials"] == "true"
    )
    assert h["access-control-expose-headers"] == "x-result" and h["vary"] == "Origin"


async def test_without_origin_and_invalid_origin(app: ASGIApp) -> None:
    assert (await req(app))[0]["status"] == 200
    assert (await req(app, headers=[(b"origin", b"https://bad")]))[0]["status"] == 403


async def test_valid_and_invalid_preflight(app: ASGIApp) -> None:
    base: list[tuple[bytes, bytes]] = [
        (b"origin", b"https://ok"),
        (b"access-control-request-method", b"POST"),
        (b"access-control-request-headers", b"Content-Type, X-Ok"),
    ]
    sent = await req(app, "OPTIONS", base)
    assert sent[0]["status"] == 204 and headers(sent)["vary"] == "Origin"
    for changed in [
        [*base[:-2], (b"access-control-request-method", b"TRACE"), *base[-1:]],
        [*base[:-1], (b"access-control-request-headers", b"x-bad")],
    ]:
        assert (await req(app, "OPTIONS", changed))[0]["status"] == 403
