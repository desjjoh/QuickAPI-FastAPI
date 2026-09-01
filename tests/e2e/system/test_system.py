import time
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.common.handlers.lifecycle_handler import ReadinessCheckResult

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(
    ("check_status", "expected_status"),
    [("up", "connected"), ("down", "disconnected")],
)
async def test_system_reports_nested_diagnostics_and_database_only_state(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    check_status: str,
    expected_status: str,
) -> None:
    check = AsyncMock(
        return_value=ReadinessCheckResult(
            name="database", status=check_status, response_time_ms=1.0  # type: ignore[arg-type]
        )
    )
    monkeypatch.setattr(app.state.lifecycle, "check_service", check)
    lag = AsyncMock(return_value=12.3456)
    monkeypatch.setattr(app.state.lifecycle, "get_event_loop_lag", lag)
    # An unrelated dependency failure must not affect the database-only field.
    monkeypatch.setattr(
        app.state.lifecycle,
        "are_all_services_healthy",
        AsyncMock(return_value=check_status != "up"),
    )
    before_ms = int(time.time() * 1_000)

    response = await client.get("/system")

    after_ms = int(time.time() * 1_000)
    assert response.status_code == 200
    payload = response.json()
    assert payload["db"] == expected_status
    assert payload["event_loop_lag"] == 12.346
    assert payload["uptime"] >= 0
    assert before_ms <= payload["timestamp"] <= after_ms
    assert set(payload["cpu"]) == {"cores", "model", "load_average"}
    assert payload["cpu"]["cores"] >= 1
    assert len(payload["cpu"]["load_average"]) == 3
    assert all(value >= 0 for value in payload["cpu"]["load_average"])
    assert set(payload["memory"]) == {
        "total_bytes",
        "available_bytes",
        "used_bytes",
        "percentage",
    }
    assert all(
        payload["memory"][field] >= 0
        for field in ("total_bytes", "available_bytes", "used_bytes")
    )
    assert 0 <= payload["memory"]["percentage"] <= 100
    assert set(payload["process"]) == {
        "rss_bytes",
        "heap_total_bytes",
        "heap_used_bytes",
        "external_bytes",
        "active_handles",
    }
    assert all(value >= 0 for value in payload["process"].values())
    assert payload["os"]["platform"]
    assert payload["os"]["release"]
    check.assert_awaited_once_with("database")
    lag.assert_awaited_once_with(samples=1, interval=0.01)
