from dataclasses import dataclass, field

import pytest

from app.common.handlers.lifecycle_handler import LifecycleHandler

pytestmark = pytest.mark.unit


@dataclass
class Service:
    name: str
    healthy: bool = True
    fail_start: bool = False
    fail_stop: bool = False
    calls: list[str] = field(default_factory=list[str])

    async def start(self) -> None:
        self.calls.append("start")
        if self.fail_start:
            raise RuntimeError("start failed")

    async def stop(self) -> None:
        self.calls.append("stop")
        if self.fail_stop:
            raise RuntimeError("stop failed")

    async def check(self) -> bool:
        self.calls.append("check")
        return self.healthy


async def test_startup_and_shutdown_update_health_and_stop_in_reverse_order() -> None:
    handler = LifecycleHandler()
    first, second = Service("first"), Service("second")
    handler.register([first, second])

    assert handler.is_alive() is True
    assert handler.is_ready() is False
    await handler.startup()
    assert handler.is_ready() is True

    await handler.shutdown()
    assert handler.is_alive() is False
    assert handler.is_ready() is False
    assert first.calls == ["start", "stop"]
    assert second.calls == ["start", "stop"]


async def test_failed_startup_rolls_back_started_services() -> None:
    handler = LifecycleHandler()
    first, broken = Service("first"), Service("broken", fail_start=True)
    handler.register([first, broken])

    with pytest.raises(RuntimeError, match="start failed"):
        await handler.startup()

    assert first.calls == ["start", "stop"]
    assert handler.is_ready() is False
    broken.fail_start = False
    await handler.startup()
    assert handler.is_ready() is True


async def test_health_checks_stop_at_first_unhealthy_service() -> None:
    handler = LifecycleHandler()
    bad, unchecked = Service("bad", healthy=False), Service("unchecked")
    handler.register([bad, unchecked])
    assert await handler.are_all_services_healthy() is False
    assert bad.calls == ["check"]
    assert unchecked.calls == []


async def test_all_services_healthy_including_empty_registration() -> None:
    handler = LifecycleHandler()
    assert await handler.are_all_services_healthy() is True
    service = Service("healthy")
    handler.register([service])
    assert await handler.are_all_services_healthy() is True


async def test_event_loop_lag_uses_each_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = LifecycleHandler()
    times = iter([0.0, 0.011, 1.0, 1.015, 2.0, 2.009])

    class Loop:
        def time(self) -> float:
            return next(times)

    sleeps: list[float] = []

    async def sleep(interval: float) -> None:
        sleeps.append(interval)

    monkeypatch.setattr(
        "app.common.handlers.lifecycle_handler.asyncio.get_running_loop", lambda: Loop()
    )
    monkeypatch.setattr("app.common.handlers.lifecycle_handler.asyncio.sleep", sleep)
    assert await handler.get_event_loop_lag(samples=3, interval=0.01) == pytest.approx(
        5.0
    )
    assert sleeps == [0.01, 0.01, 0.01]
    assert await handler.get_event_loop_lag(samples=0) == 0.0


async def test_repeated_registration_startup_and_shutdown_are_idempotent() -> None:
    handler = LifecycleHandler()
    service = Service("same")
    handler.register([service, service])
    await handler.startup()
    await handler.startup()
    await handler.shutdown()
    await handler.shutdown()
    assert service.calls == ["start", "stop"]


async def test_shutdown_continues_after_stop_failure() -> None:
    handler = LifecycleHandler()
    first, broken = Service("first"), Service("broken", fail_stop=True)
    handler.register([first, broken])
    await handler.startup()
    await handler.shutdown()
    assert first.calls[-1] == "stop"
