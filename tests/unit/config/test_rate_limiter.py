from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from app.common.store.rate_limit import RateLimitDecision, RateLimitUsage
from app.config.rate_limiter import RateLimiter

pytestmark = pytest.mark.unit


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_exact_rolling_boundary_and_ring_wraparound() -> None:
    clock = Clock()
    limiter = RateLimiter(window_ms=1000, max_requests=2, clock=clock)
    assert limiter.admit("a").allowed
    clock.now = 500
    assert limiter.admit("a").allowed
    clock.now = 999
    assert limiter.admit("a") == RateLimitDecision(False, 429, 1)
    clock.now = 1000
    assert limiter.admit("a").allowed
    clock.now = 1499
    assert not limiter.admit("a").allowed
    clock.now = 1500
    assert limiter.admit("a").allowed
    for time in range(2000, 10000, 500):
        clock.now = time
        assert limiter.admit("a").allowed
        assert limiter.usage == RateLimitUsage(1, 2, 2)


def test_rejected_flood_neither_grows_history_nor_extends_expiry() -> None:
    clock = Clock()
    limiter = RateLimiter(window_ms=1000, max_requests=2, max_clients=2, clock=clock)
    limiter.admit("a")
    limiter.admit("a")
    clock.now = 900
    for _ in range(20000):
        assert limiter.admit("a") == RateLimitDecision(False, 429, 1)
    assert limiter.usage == RateLimitUsage(1, 2, 2)
    clock.now = 1000
    assert limiter.admit("a").allowed
    assert limiter.usage == RateLimitUsage(1, 1, 2)


def test_new_identity_flood_preserves_active_quotas_then_recovers() -> None:
    clock = Clock()
    limiter = RateLimiter(window_ms=2500, max_requests=1, max_clients=3, clock=clock)
    for identity in ["a", "b", "c"]:
        assert limiter.admit(identity).allowed
    clock.now = 1001
    for index in range(10000):
        assert limiter.admit(f"new-{index}") == RateLimitDecision(False, 503, 2)
    assert limiter.usage == RateLimitUsage(3, 3, 3)
    assert limiter.admit("a").status == 429
    clock.now = 2500
    assert limiter.admit("new").allowed
    assert limiter.usage == RateLimitUsage(1, 1, 1)


def test_last_admission_orders_capacity_recovery_and_tracked_clients_can_continue() -> (
    None
):
    clock = Clock()
    limiter = RateLimiter(window_ms=5000, max_requests=2, max_clients=2, clock=clock)
    limiter.admit("a")
    clock.now = 1000
    limiter.admit("b")
    clock.now = 2000
    assert limiter.admit("a").allowed
    assert limiter.admit("c") == RateLimitDecision(False, 503, 4)
    clock.now = 5999
    assert limiter.admit("b").allowed
    assert limiter.admit("c") == RateLimitDecision(False, 503, 2)
    clock.now = 7000
    assert limiter.admit("c").allowed
    assert limiter.admit("b").allowed
    assert limiter.admit("b").status == 429


def test_independent_instances_and_long_identities_are_bounded() -> None:
    identity = "long-identity-" * 10000
    first = RateLimiter(max_requests=1, max_clients=1)
    second = RateLimiter(max_requests=1, max_clients=1)
    assert first.admit(identity).allowed
    assert first.admit(identity).status == 429
    assert first.admit(identity + "new").status == 503
    assert second.admit(identity).allowed
    assert first.usage == second.usage == RateLimitUsage(1, 1, 1)


def test_concurrent_access_never_exceeds_quota_or_client_capacity() -> None:
    limiter = RateLimiter(max_requests=5, max_clients=1)
    with ThreadPoolExecutor(max_workers=16) as executor:
        decisions = list(executor.map(limiter.admit, ["shared"] * 500))
    assert sum(decision.allowed for decision in decisions) == 5
    assert limiter.usage == RateLimitUsage(1, 5, 5)
    other = RateLimiter(max_requests=5, max_clients=2)
    with ThreadPoolExecutor(max_workers=16) as executor:
        distinct = list(
            executor.map(other.admit, [f"client-{index}" for index in range(100)])
        )
    assert sum(decision.allowed for decision in distinct) == 2
    assert other.usage == RateLimitUsage(2, 2, 10)


@pytest.mark.parametrize(
    "options",
    [
        {"window_ms": 0},
        {"window_ms": 86400001},
        {"max_requests": 0},
        {"max_requests": 10001},
        {"max_clients": 0},
        {"max_clients": 100001},
        {"max_requests": 201, "max_clients": 10000},
    ],
)
def test_direct_construction_rejects_invalid_storage(options: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        RateLimiter(
            window_ms=options.get("window_ms", 60000),
            max_requests=options.get("max_requests", 200),
            max_clients=options.get("max_clients", 10000),
        )
