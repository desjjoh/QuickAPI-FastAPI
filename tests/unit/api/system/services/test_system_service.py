# pyright: reportPrivateUsage=false

import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from unittest.mock import AsyncMock

import pytest

from app.api.system.services import system_service
from app.api.system.services.system_service import (
    SystemDiagnosticsService,
    SystemService,
)
from app.common.handlers.lifecycle_handler import LifecycleHandler, ReadinessCheckResult

pytestmark = pytest.mark.unit


def test_liveness_uses_application_start_and_never_checks_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialized = datetime(2026, 1, 1, tzinfo=UTC)
    lifecycle = LifecycleHandler()
    checks = AsyncMock(side_effect=AssertionError('Liveness checked dependencies'))

    monkeypatch.setattr(lifecycle, 'check_services', checks)
    service = SystemService(lifecycle, initialized, 10)

    monkeypatch.setattr(system_service.time, 'perf_counter', lambda: 11.23456)
    result = service.live()

    assert result['alive'] is True
    assert result['uptime'] == 1.235
    assert result['timestamp'] == initialized + timedelta(seconds=1.235)
    checks.assert_not_awaited()


@pytest.mark.parametrize(
    'started,healthy', [(False, True), (True, False), (True, True)]
)
async def test_readiness_requires_startup_and_healthy_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    started: bool,
    healthy: bool,
) -> None:
    lifecycle = LifecycleHandler()

    if started:
        await lifecycle.startup()

    checks = AsyncMock(
        return_value=[ReadinessCheckResult('database', 'up' if healthy else 'down', 0)]
    )

    monkeypatch.setattr(lifecycle, 'check_services', checks)
    service = SystemService(lifecycle, datetime.now(UTC), time.perf_counter())
    result = await service.ready()

    assert result == (started and healthy)
    checks.assert_awaited_once()


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
    assert system_service._memory_diagnostics() == {
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


def test_proc_memory_invalid_or_incomplete_data_returns_none(tmp_path: object) -> None:
    from pathlib import Path

    missing = Path(str(tmp_path)) / "missing"
    incomplete = Path(str(tmp_path)) / "meminfo"

    incomplete.write_text("MemTotal: 100 kB\n", encoding="ascii")

    assert system_service._memory_from_proc(missing) is None
    assert system_service._memory_from_proc(incomplete) is None


@pytest.mark.parametrize("failure", [OSError(), -1])
def test_sysconf_failure_returns_none(
    failure: Exception | int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_name: str) -> int:
        if isinstance(failure, Exception):
            raise failure

        return failure

    monkeypatch.setattr(system_service.os, "sysconf", fail, raising=False)
    assert system_service._memory_from_sysconf() is None


def test_rss_unit_conversion() -> None:
    assert system_service._rss_bytes(7, "Darwin") == 7
    assert system_service._rss_bytes(7, "Linux") == 7 * 1024
    assert system_service._rss_bytes(-1, "Linux") == 0


def test_resource_module_absent_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> object:
        raise ImportError

    monkeypatch.setattr(system_service.importlib, "import_module", missing)
    assert system_service._process_rss_bytes() == 0


def test_resource_read_failure_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingResourceModule:
        RUSAGE_SELF = 0

        @staticmethod
        def getrusage(_who: int) -> object:
            raise OSError

    def load_failing_resource(_name: str) -> object:
        return FailingResourceModule()

    monkeypatch.setattr(
        system_service.importlib, "import_module", load_failing_resource
    )
    assert system_service._process_rss_bytes() == 0


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


async def test_diagnostic_check_failures_return_safe_values() -> None:
    lifecycle = Lifecycle()
    lifecycle.get_event_loop_lag = AsyncMock(side_effect=RuntimeError)
    lifecycle.check_service = AsyncMock(side_effect=RuntimeError)
    service = SystemDiagnosticsService(lifecycle, time.perf_counter())  # type: ignore[arg-type]

    assert await service._event_loop_lag() == 0.0
    assert await service._database_status() == "disconnected"


def test_diagnostics_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        SystemDiagnosticsService(Lifecycle(), time.perf_counter(), timeout_seconds=0)  # type: ignore[arg-type]


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

    assert response['cpu']['cores'] == 1
    assert response['cpu']['load_average'] == (0.0, 0.0, 0.0)
    assert response['memory']['total_bytes'] == 0
    assert response['process']['rss_bytes'] == 0
    assert response['db'] == "disconnected"
