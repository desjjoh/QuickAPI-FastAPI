import pytest
from conftest import http_scope, invoke
from starlette.types import ASGIApp

from app.common.middleware.request_header_limit import (
    HeaderLimits,
    RequestHeaderLimitASGIMiddleware,
)

pytestmark = pytest.mark.unit


def middleware(app: ASGIApp, limits: HeaderLimits) -> RequestHeaderLimitASGIMiddleware:
    return RequestHeaderLimitASGIMiddleware(app, limits)


@pytest.mark.parametrize(
    "headers,limits,status",
    [
        (
            [(b"a", b"1"), (b"b", b"2")],
            HeaderLimits(
                max_header_count=2, max_single_header_bytes=9, max_total_header_bytes=9
            ),
            200,
        ),
        (
            [(b"a", b"1"), (b"b", b"2"), (b"c", b"3")],
            HeaderLimits(
                max_header_count=2, max_single_header_bytes=9, max_total_header_bytes=9
            ),
            431,
        ),
        (
            [(b"abc", b"12")],
            HeaderLimits(
                max_header_count=2, max_single_header_bytes=5, max_total_header_bytes=9
            ),
            200,
        ),
        (
            [(b"abc", b"123")],
            HeaderLimits(
                max_header_count=2, max_single_header_bytes=5, max_total_header_bytes=9
            ),
            431,
        ),
        (
            [(b"aa", b"11"), (b"b", b"222")],
            HeaderLimits(
                max_header_count=2, max_single_header_bytes=5, max_total_header_bytes=8
            ),
            200,
        ),
        (
            [(b"aa", b"11"), (b"bb", b"222")],
            HeaderLimits(
                max_header_count=2, max_single_header_bytes=5, max_total_header_bytes=8
            ),
            431,
        ),
    ],
)
async def test_boundaries(
    app: ASGIApp,
    headers: list[tuple[bytes, bytes]],
    limits: HeaderLimits,
    status: int,
) -> None:
    assert (await invoke(middleware(app, limits), http_scope(headers)))[0][
        "status"
    ] == status


async def test_chunked_casing_duplicate_and_non_ascii_are_counted(app: ASGIApp) -> None:
    base = HeaderLimits(
        max_header_count=3, max_single_header_bytes=50, max_total_header_bytes=100
    )
    assert (
        await invoke(
            middleware(app, base), http_scope([(b"Transfer-Encoding", b"Chunked")])
        )
    )[0]["status"] == 501
    assert (
        await invoke(
            middleware(
                app,
                HeaderLimits(
                    max_header_count=3,
                    max_single_header_bytes=50,
                    max_total_header_bytes=100,
                    allow_chunked=True,
                ),
            ),
            http_scope([(b"transfer-encoding", b"chunked"), (b"x", b"\xff")]),
        )
    )[0]["status"] == 200
