from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.e2e


def assert_unavailable(response: httpx.Response, message: str) -> None:
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == 503
    assert payload["message"] == message
    assert isinstance(payload["timestamp"], int)
    assert payload["timestamp"] > 0


async def test_readiness_succeeds_when_started_and_healthy(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"ready": True}


async def test_readiness_rejects_an_application_that_has_not_started(
    app: FastAPI,
) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert_unavailable(response, "Application not ready.")


async def test_readiness_rejects_an_unhealthy_service(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app.state.lifecycle, "are_all_services_healthy", AsyncMock(return_value=False)
    )

    response = await client.get("/ready")

    assert_unavailable(response, "One or more lifecycle services are unhealthy.")
