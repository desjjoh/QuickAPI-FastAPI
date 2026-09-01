# pyright: reportPrivateUsage=false

import time
from typing import Literal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.api.system.models.system_model import CpuDiagnostics, MemoryDiagnostics
from app.api.system.services import system_service
from app.api.system.services.system_service import SystemDiagnosticsService
from app.common.handlers.lifecycle_handler import ReadinessCheckResult

pytestmark = pytest.mark.unit


class Lifecycle:
    check_service = AsyncMock()
    get_event_loop_lag = AsyncMock(return_value=0.0)


def test_load_average_and_memory_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    def unsupported() -> tuple[float, float, float]:
        raise OSError

    monkeypatch.setattr(system_service.os, "getloadavg", unsupported, raising=False)
    monkeypatch.setattr(system_service, "_memory_from_proc", lambda: None)
    monkeypatch.setattr(system_service, "_memory_from_sysconf", lambda: None)
    assert system_service._load_average() == (0.0, 0.0, 0.0)
    assert system_service._memory_diagnostics().model_dump() == {
        "total_bytes": 0,
        "available_bytes": 0,
        "used_bytes": 0,
        "percentage": 0.0,
    }


def test_platform_functions_absent_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(system_service.os, "getloadavg", raising=False)
    monkeypatch.delattr(system_service.os, "sysconf", raising=False)
    assert system_service._load_average() == (0.0, 0.0, 0.0)
    assert system_service._memory_from_sysconf() is None


def test_proc_memory_compatibility_helper(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "meminfo"
    path.write_text("MemTotal: 100 kB\nMemAvailable: 25 kB\n", encoding="ascii")
    assert system_service._memory_from_proc(path) == (102400, 25600)


def test_rss_unit_conversion() -> None:
    assert system_service._rss_bytes(7, "Darwin") == 7
    assert system_service._rss_bytes(7, "Linux") == 7 * 1024
    assert system_service._rss_bytes(-1, "Linux") == 0


def test_resource_module_absent_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> object:
        raise ImportError

    monkeypatch.setattr(system_service.importlib, "import_module", missing)
    assert system_service._process_rss_bytes() == 0


def test_nested_model_ranges_and_fixed_load_average() -> None:
    CpuDiagnostics(cores=1, model="unknown", load_average=(0.0, 1.0, 2.0))
    MemoryDiagnostics(total_bytes=1, available_bytes=1, used_bytes=0, percentage=100.0)
    with pytest.raises(ValidationError):
        CpuDiagnostics(cores=0, model="x", load_average=(0.0, 0.0, 0.0))
    with pytest.raises(ValidationError):
        CpuDiagnostics(cores=1, model="x", load_average=(0.0, 0.0))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        MemoryDiagnostics(
            total_bytes=1, available_bytes=0, used_bytes=1, percentage=101.0
        )


@pytest.mark.parametrize(
    ("result", "expected"), [("up", "connected"), ("down", "disconnected")]
)
async def test_database_status_uses_only_named_database_check(
    result: Literal["up", "down"], expected: str
) -> None:
    lifecycle = Lifecycle()
    lifecycle.check_service = AsyncMock(
        return_value=ReadinessCheckResult(
            name="database", status=result, response_time_ms=0.0
        )
    )
    service = SystemDiagnosticsService(lifecycle, time.perf_counter())  # type: ignore[arg-type]
    assert await service._database_status() == expected
    lifecycle.check_service.assert_awaited_once_with("database")


async def test_event_loop_lag_is_non_negative() -> None:
    lifecycle = Lifecycle()
    lifecycle.get_event_loop_lag = AsyncMock(return_value=3.5)
    service = SystemDiagnosticsService(lifecycle, time.perf_counter())  # type: ignore[arg-type]
    assert await service._event_loop_lag() == 3.5
    lifecycle.get_event_loop_lag.assert_awaited_once_with(samples=1, interval=0.01)


async def test_collector_timeout_returns_required_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = Lifecycle()
    lifecycle.check_service = AsyncMock(return_value=None)

    def slow() -> object:
        time.sleep(0.03)
        return system_service._fallback_diagnostics()

    monkeypatch.setattr(system_service, "_sync_diagnostics", slow)
    service = SystemDiagnosticsService(lifecycle, time.perf_counter(), timeout_seconds=0.001)  # type: ignore[arg-type]
    response = await service.collect()
    assert response.cpu.cores == 1
    assert response.cpu.load_average == (0.0, 0.0, 0.0)
    assert response.memory.total_bytes == 0
    assert response.process.rss_bytes == 0
    assert response.db == "disconnected"
