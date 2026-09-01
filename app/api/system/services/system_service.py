import asyncio
import importlib
import os
import platform
import socket
import sys
import time
import tracemalloc
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Literal, Protocol, cast

from app.api.system.models.info_model import InfoResponse
from app.api.system.models.system_model import (
    CpuDiagnostics,
    MemoryDiagnostics,
    OsDiagnostics,
    ProcessDiagnostics,
    SystemResponse,
)
from app.common.handlers.lifecycle_handler import LifecycleHandler
from app.config.environment import settings

LoadAverageFunction = Callable[[], tuple[float, float, float]]
SysconfFunction = Callable[[str], int]


class _ResourceUsage(Protocol):
    ru_maxrss: int | float


class _ResourceModule(Protocol):
    RUSAGE_SELF: int

    def getrusage(self, who: int) -> _ResourceUsage: ...


class SystemInfoService:
    """Build the public, non-secret application runtime identity."""

    def __init__(self, started_at: datetime) -> None:
        self._started_at = started_at

    def info(self) -> InfoResponse:
        return InfoResponse(
            name=settings.APP_NAME,
            version=settings.APP_VERSION,
            environment=settings.ENV,
            hostname=socket.gethostname(),
            pid=os.getpid(),
            python_version=platform.python_version() or sys.version.split()[0],
            platform=platform.system() or sys.platform,
            architecture=platform.machine() or "unknown",
            started_at=self._started_at,
            timezone=settings.TIMEZONE,
        )


def _load_average() -> tuple[float, float, float]:
    """Return the conventional load triple, or deterministic portable values."""
    getloadavg = cast(LoadAverageFunction | None, getattr(os, "getloadavg", None))
    if getloadavg is None:
        return (0.0, 0.0, 0.0)
    try:
        values: tuple[float, float, float] = getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)
    first, second, third = values
    return max(0.0, first), max(0.0, second), max(0.0, third)


def _memory_from_proc(path: Path = Path("/proc/meminfo")) -> tuple[int, int] | None:
    """Read total and available bytes from Linux procfs when it is usable."""
    try:
        entries = {
            parts[0].rstrip(":"): int(parts[1]) * 1024
            for line in path.read_text(encoding="ascii").splitlines()
            if len(parts := line.split()) >= 2 and parts[1].isdigit()
        }
    except (OSError, ValueError):
        return None
    total = entries.get("MemTotal")
    available = entries.get("MemAvailable", entries.get("MemFree"))
    if total is None or available is None:
        return None
    return max(0, total), min(max(0, available), max(0, total))


def _memory_from_sysconf() -> tuple[int, int] | None:
    """Use portable POSIX page counters, where the host exposes both counters."""
    sysconf = cast(SysconfFunction | None, getattr(os, "sysconf", None))
    if sysconf is None:
        return None
    try:
        page_size = sysconf("SC_PAGE_SIZE")
        pages = sysconf("SC_PHYS_PAGES")
        available_pages = sysconf("SC_AVPHYS_PAGES")
    except (OSError, ValueError):
        return None
    if min(page_size, pages, available_pages) < 0:
        return None
    total = page_size * pages
    return total, min(page_size * available_pages, total)


def _memory_diagnostics() -> MemoryDiagnostics:
    total, available = _memory_from_proc() or _memory_from_sysconf() or (0, 0)
    used = max(0, total - available)
    percentage = min(100.0, max(0.0, used * 100.0 / total)) if total else 0.0
    return MemoryDiagnostics(
        total_bytes=total,
        available_bytes=available,
        used_bytes=used,
        percentage=percentage,
    )


def _rss_bytes(max_rss: int | float, system: str | None = None) -> int:
    """Convert getrusage.ru_maxrss to bytes (bytes on macOS, KiB elsewhere)."""
    value = max(0, int(max_rss))
    return value if (system or platform.system()) == "Darwin" else value * 1024


def _process_rss_bytes() -> int:
    """Return process resident-set size, or zero where resource is unavailable."""
    try:
        module: ModuleType = importlib.import_module("resource")
    except ImportError:
        return 0

    resource_module = cast(_ResourceModule, cast(object, module))
    try:
        usage = resource_module.getrusage(resource_module.RUSAGE_SELF)
    except (AttributeError, OSError, ValueError):
        return 0
    return _rss_bytes(usage.ru_maxrss)


def _sync_diagnostics() -> (
    tuple[CpuDiagnostics, MemoryDiagnostics, ProcessDiagnostics, OsDiagnostics]
):
    current, peak = (
        tracemalloc.get_traced_memory() if tracemalloc.is_tracing() else (0, 0)
    )
    processor = platform.processor() or "unknown"
    system = platform.system() or "unknown"
    release = platform.release() or "unknown"
    return (
        CpuDiagnostics(
            # os.cpu_count() may legally return None; one is the documented floor.
            cores=max(1, os.cpu_count() or 1),
            model=processor,
            load_average=_load_average(),
        ),
        _memory_diagnostics(),
        ProcessDiagnostics(
            rss_bytes=_process_rss_bytes(),
            heap_total_bytes=max(0, peak),
            heap_used_bytes=max(0, current),
            external_bytes=0,
            active_handles=0,  # populated from the event-loop thread below
        ),
        OsDiagnostics(platform=system, release=release),
    )


def _fallback_diagnostics() -> (
    tuple[CpuDiagnostics, MemoryDiagnostics, ProcessDiagnostics, OsDiagnostics]
):
    return (
        CpuDiagnostics(cores=1, model="unknown", load_average=(0.0, 0.0, 0.0)),
        MemoryDiagnostics(
            total_bytes=0, available_bytes=0, used_bytes=0, percentage=0.0
        ),
        ProcessDiagnostics(
            rss_bytes=0,
            heap_total_bytes=0,
            heap_used_bytes=0,
            external_bytes=0,
            active_handles=0,
        ),
        OsDiagnostics(platform="unknown", release="unknown"),
    )


class SystemDiagnosticsService:
    """Collect bounded diagnostics without blocking the asyncio event loop."""

    def __init__(
        self,
        lifecycle: LifecycleHandler,
        started_at: float,
        timeout_seconds: float = 0.25,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._lifecycle = lifecycle
        self._started_at = started_at
        self._timeout_seconds = timeout_seconds

    async def _event_loop_lag(self) -> float:
        """Measure lag through the lifecycle's public, tested asyncio sampler."""
        try:
            lag = await asyncio.wait_for(
                self._lifecycle.get_event_loop_lag(samples=1, interval=0.01),
                timeout=self._timeout_seconds,
            )
        except Exception:
            return 0.0
        return max(0.0, lag)

    async def _database_status(self) -> Literal["connected", "disconnected"]:
        try:
            result = await asyncio.wait_for(
                self._lifecycle.check_service("database"),
                timeout=self._timeout_seconds,
            )
        except Exception:
            return "disconnected"
        return "connected" if result is not None and result.is_up else "disconnected"

    async def collect(self) -> SystemResponse:
        db_task = asyncio.create_task(self._database_status())
        lag_task = asyncio.create_task(self._event_loop_lag())
        try:
            diagnostics = await asyncio.wait_for(
                asyncio.to_thread(_sync_diagnostics), timeout=self._timeout_seconds
            )
        except Exception:
            diagnostics = _fallback_diagnostics()

        cpu, memory, process, os_data = diagnostics
        process = process.model_copy(
            update={
                "active_handles": len(
                    [task for task in asyncio.all_tasks() if not task.done()]
                )
            }
        )
        db, lag = await asyncio.gather(db_task, lag_task)
        return SystemResponse(
            uptime=round(max(0.0, time.perf_counter() - self._started_at), 3),
            timestamp=int(time.time() * 1000),
            event_loop_lag=round(max(0.0, lag), 3),
            db=db,
            cpu=cpu,
            memory=memory,
            process=process,
            os=os_data,
        )
