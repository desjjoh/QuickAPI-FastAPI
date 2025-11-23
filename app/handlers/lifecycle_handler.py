import asyncio
import signal
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.config.logging import log

ShutdownFn = Callable[[], Awaitable[None]]
StartFn = Callable[[], Awaitable[None]]
CheckFn = Callable[[], Awaitable[bool]]


class LifecycleService(Protocol):
    name: str

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def check(self) -> bool: ...


class LifecycleHandler:

    def __init__(self) -> None:
        self._services: list[LifecycleService] = []

        self._service_health: dict[str, bool] = {}

        self._startup_started = False
        self._startup_completed = False
        self._shutdown_started = False

    def is_alive(self) -> bool:
        return not self._shutdown_started

    def is_ready(self) -> bool:
        return self._startup_completed and not self._shutdown_started

    async def are_all_services_healthy(self) -> bool:
        for svc in self._services:
            healthy = await svc.check()
            if not healthy:
                return False
        return True

    async def get_event_loop_lag(
        self,
        samples: int = 5,
        interval: float = 0.02,
    ) -> float:
        loop = asyncio.get_running_loop()
        delays: list[float] = []

        for _ in range(samples):
            start = loop.time()
            await asyncio.sleep(interval)
            end = loop.time()
            delay = max(0.0, (end - start) - interval)
            delays.append(delay)

        return max(delays) * 1000.0 if delays else 0.0

    def register(self, services: list[LifecycleService]) -> None:
        start = time.perf_counter()
        log.debug(f"Registering lifecycle services ({len(services)} total)")

        self._services.extend(services)

        duration = (time.perf_counter() - start) * 1000
        log.debug(f"Lifecycle registration completed in {duration:.2f}ms")

    async def startup(self) -> None:
        if self._startup_started:
            return
        self._startup_started = True

        start = time.perf_counter()
        log.debug('Starting services…')

        for svc in self._services:
            try:
                await svc.start()
                log.debug(f"Service started → {svc.name}")
            except Exception:
                log.error("Service failed to start")
                raise

        self._startup_completed = True

        duration = (time.perf_counter() - start) * 1000
        log.debug(f"All services started in {duration:.2f}ms")

    async def shutdown(self, sig: signal.Signals | None = None) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True

        start = time.perf_counter()

        log.debug("Stopping services…")

        for svc in reversed(self._services):
            try:
                await svc.stop()
                log.debug(f"Service stopped ← {svc.name}")
            except Exception:
                log.warning("Failed to stop service cleanly")

        duration = (time.perf_counter() - start) * 1000
        log.debug(f"Shutdown completed in {duration:.2f}ms")


lifecycle = LifecycleHandler()
