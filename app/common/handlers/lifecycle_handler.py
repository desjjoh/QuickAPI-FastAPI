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

        self._service_names: set[str] = set()
        self._started_services: list[LifecycleService] = []

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

        for service in services:
            if service.name in self._service_names:
                log.debug(f"Lifecycle service already registered → {service.name}")
                continue

            self._services.append(service)
            self._service_names.add(service.name)

        duration = (time.perf_counter() - start) * 1000
        log.debug(f"Lifecycle registration completed in {duration:.2f}ms")

    async def startup(self) -> None:
        if self._startup_started:
            return
        self._startup_started = True
        self._shutdown_started = False
        self._startup_completed = False
        self._started_services.clear()

        start = time.perf_counter()
        log.debug('Starting services…')

        try:
            for svc in self._services:
                await svc.start()
                self._started_services.append(svc)
                log.debug(f"Service started → {svc.name}")
        except Exception:
            log.warning("Service startup failed — rolling back started services")
            await self._stop_started_services()
            self._startup_started = False
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

        await self._stop_started_services()

        self._startup_started = False
        self._startup_completed = False

        duration = (time.perf_counter() - start) * 1000
        log.debug(f"Shutdown completed in {duration:.2f}ms")

    async def _stop_started_services(self) -> None:
        while self._started_services:
            svc = self._started_services.pop()
            try:
                await svc.stop()
                log.debug(f"Service stopped ← {svc.name}")
            except Exception as exc:
                error_type = exc.__class__.__name__
                error_msg = getattr(exc, "msg", None) or str(exc).split("\n")[0]
                log.error(f"{error_type} — {error_msg}")

                log.warning(f"Failed to stop service ← {svc.name}")
