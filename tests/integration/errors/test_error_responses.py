import time
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException

from app.config.database import get_session

pytestmark = pytest.mark.integration

FORBIDDEN_TEXT = (
    "traceback",
    "runtimeerror",
    "sqlalchemy",
    "sqlite",
    "select ",
    "password",
    "submitted-secret",
)


def assert_error_contract(
    response: httpx.Response,
    status: int,
    message: str | None = None,
    *,
    started_ms: int,
) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {"status", "message", "timestamp"}
    assert body["status"] == response.status_code
    assert isinstance(body["message"], str)
    if message is not None:
        assert body["message"] == message
    assert type(body["timestamp"]) is int
    assert started_ms <= body["timestamp"] <= int(time.time() * 1000)
    lowered = response.text.lower()
    assert all(value not in lowered for value in FORBIDDEN_TEXT)


@pytest.mark.parametrize(
    ("method", "url", "kwargs", "status", "message_fragment"),
    [
        ("GET", "/missing", {}, 404, "Not Found"),
        ("DELETE", "/health", {}, 405, "Method Not Allowed"),
        ("GET", "/api/v1/items/not-hex", {}, 422, "path.id"),
        ("GET", "/api/v1/items/", {"params": {"page": 0}}, 422, "query.page"),
        (
            "POST",
            "/api/v1/items/",
            {"json": {"name": "submitted-secret", "price": -1}},
            422,
            "body.price",
        ),
    ],
)
async def test_routing_and_validation_errors_are_complete_envelopes(
    error_client: httpx.AsyncClient,
    method: str,
    url: str,
    kwargs: dict[str, Any],
    status: int,
    message_fragment: str,
) -> None:
    started = int(time.time() * 1000)
    response = await error_client.request(method, url, **kwargs)
    assert_error_contract(response, status, started_ms=started)
    assert message_fragment in response.json()["message"]
    assert response.headers["x-request-id"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-ratelimit-result"] == "accepted"
    if status == 405:
        assert response.headers["allow"] == "GET"


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("plain detail", "plain detail"),
        ({"reason": "structured", "code": 7}, '{"code":7,"reason":"structured"}'),
        (["first", {"reason": "nested"}], '["first",{"reason":"nested"}]'),
        (42, "42"),
    ],
)
async def test_http_exception_supported_detail_shapes(
    error_app: FastAPI,
    error_client: httpx.AsyncClient,
    detail: Any,
    expected: str,
) -> None:
    router = APIRouter()

    @router.get(f"/explicit/{abs(hash(expected))}")
    async def explicit() -> None:
        raise HTTPException(409, detail=detail, headers={"X-Error-Marker": "kept"})

    error_app.include_router(router)
    started = int(time.time() * 1000)
    response = await error_client.get(f"/explicit/{abs(hash(expected))}")
    assert_error_contract(response, 409, expected, started_ms=started)
    assert response.headers["x-error-marker"] == "kept"


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("submitted-secret"), Exception("SELECT password FROM users")],
)
async def test_repository_and_unexpected_failures_do_not_leak(
    error_app: FastAPI,
    error_client: httpx.AsyncClient,
    failure: Exception,
) -> None:
    async def broken_session() -> Any:
        raise failure

    error_app.dependency_overrides[get_session] = broken_session
    started = int(time.time() * 1000)
    response = await error_client.get("/api/v1/items/")
    assert_error_contract(response, 500, "Internal server error.", started_ms=started)


async def test_unexpected_route_exception_is_sanitized(
    error_app: FastAPI, error_client: httpx.AsyncClient
) -> None:
    @error_app.get("/unexpected-error")
    async def unexpected() -> None:
        raise RuntimeError("submitted-secret database password")

    started = int(time.time() * 1000)
    response = await error_client.get("/unexpected-error")
    assert_error_contract(response, 500, "Internal server error.", started_ms=started)


async def test_protocol_headers_survive_an_error_response(
    error_client: httpx.AsyncClient,
) -> None:
    response = await error_client.get(
        "/missing", headers={"origin": "https://client.example"}
    )
    assert response.headers["access-control-allow-origin"] == "https://client.example"
    assert response.headers["vary"] == "Origin"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]
    assert response.headers["x-ratelimit-result"] == "accepted"
