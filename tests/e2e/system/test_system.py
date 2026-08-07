import time
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(
    ("healthy", "expected_status"),
    [(True, "connected"), (False, "disconnected")],
)
async def test_system_reports_service_state_timestamp_and_controlled_lag(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    healthy: bool,
    expected_status: str,
) -> None:
    monkeypatch.setattr(
        app.state.lifecycle,
        "are_all_services_healthy",
        AsyncMock(return_value=healthy),
    )
    lag = AsyncMock(return_value=12.3456)
    monkeypatch.setattr(app.state.lifecycle, "get_event_loop_lag", lag)
    before_ms = int(time.time() * 1_000)

    response = await client.get("/system")

    after_ms = int(time.time() * 1_000)
    assert response.status_code == 200
    payload = response.json()
    assert payload["db"] == expected_status
    assert payload["event_loop_lag"] == 12.346
    assert payload["uptime"] >= 0
    assert before_ms <= payload["timestamp"] <= after_ms
    assert payload["timestamp"] > 1_000_000_000_000  # milliseconds, not seconds
    lag.assert_awaited_once_with(samples=1)
