from concurrent.futures import ThreadPoolExecutor

import pytest

from app.common.store import rate_limit as rate_limit_state
from app.config import rate_limiter
from app.config.rate_limiter import RateLimiter

pytestmark = pytest.mark.unit


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def limiter(monkeypatch: pytest.MonkeyPatch) -> tuple[RateLimiter, Clock]:
    clock = Clock()
    monkeypatch.setattr(rate_limiter, "monotonic", clock)
    monkeypatch.setattr(rate_limit_state, "monotonic", clock)
    return (
        RateLimiter(max_burst=2, burst_window=5, max_sustained=2, sustained_period=10),
        clock,
    )


def test_capacity_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    subject, _ = limiter(monkeypatch)
    assert [subject.allow("one") for _ in range(3)] == [True, True, False]


def test_burst_window_and_sustained_tokens_refill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject, clock = limiter(monkeypatch)
    assert subject.allow("one") and subject.allow("one")
    clock.now = 4
    assert subject.allow("one") is False  # neither window has replenished a full token
    clock.now = 5
    assert subject.allow("one") is True


def test_keys_have_independent_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    subject, _ = limiter(monkeypatch)
    assert subject.allow("a") and subject.allow("a")
    assert subject.allow("a") is False
    assert subject.allow("b") is True


def test_gc_removes_only_inactive_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    subject, clock = limiter(monkeypatch)
    subject.gc_interval = 1
    subject.allow("old")
    clock.now = 30
    subject.allow("recent")
    clock.now = 61
    subject.allow("recent")
    clients: dict[str, object] = subject.__dict__["_clients"]
    assert "old" not in clients
    assert "recent" in clients


def test_concurrent_access_never_exceeds_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject, _ = limiter(monkeypatch)
    with ThreadPoolExecutor(max_workers=16) as executor:
        accepted = list(executor.map(subject.allow, ["shared"] * 100))
    assert sum(accepted) == 2
