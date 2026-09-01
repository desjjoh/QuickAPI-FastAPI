from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.e2e


def assert_health_payload(response: httpx.Response, *, alive: bool) -> None:
    assert response.status_code == 200
    payload = response.json()
    assert payload.keys() == {"alive", "status", "uptime", "timestamp"}
    assert payload["alive"] is alive
    assert payload["status"] == ("alive" if alive else "dead")
    assert isinstance(payload["alive"], bool)
    assert isinstance(payload["uptime"], float)
    assert payload["uptime"] >= 0
    timestamp = datetime.fromisoformat(payload["timestamp"])
    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() == timedelta(0)


async def test_health_reports_alive_before_startup(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert_health_payload(await client.get("/health"), alive=True)


async def test_health_reports_alive_during_lifespan(client: httpx.AsyncClient) -> None:
    assert_health_payload(await client.get("/health"), alive=True)


async def test_health_ignores_dependency_failure(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency_check = AsyncMock(return_value=False)
    monkeypatch.setattr(
        app.state.lifecycle,
        "are_all_services_healthy",
        dependency_check,
    )

    assert_health_payload(await client.get("/health"), alive=True)
    dependency_check.assert_not_awaited()


async def test_health_reports_dead_after_shutdown(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        pass

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert_health_payload(await client.get("/health"), alive=False)
