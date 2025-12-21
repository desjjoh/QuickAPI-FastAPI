from __future__ import annotations

from time import monotonic

from app.common.store.rate_limit import RateLimitState


class RateLimiter:
    def __init__(
        self,
        max_burst: int = 10,
        burst_window: float = 5.0,
        max_sustained: int = 100,
        sustained_period: float = 60.0,
        gc_interval: float = 120.0,
    ):
        self.max_burst = max_burst
        self.burst_window = burst_window
        self.max_sustained = max_sustained
        self.sustained_period = sustained_period
        self.gc_interval = gc_interval

        self._clients: dict[str, RateLimitState] = {}
        self._last_gc = monotonic()

    def _get_state(self, ip: str) -> RateLimitState:
        state: RateLimitState | None = self._clients.get(ip)

        if state is None:
            state = RateLimitState.new(self.max_burst, self.max_sustained)
            self._clients[ip] = state

        return state

    def _refill(self, state: RateLimitState) -> None:
        now: float = monotonic()
        elapsed: float = now - state.last_refill

        if elapsed > 0:
            refill_rate = self.max_sustained / self.sustained_period
            state.last_refill = now
            state.sustained_tokens = min(
                self.max_sustained,
                state.sustained_tokens + elapsed * refill_rate,
            )

        if (now - state.last_burst_reset) >= self.burst_window:
            state.burst_tokens = self.max_burst
            state.last_burst_reset = now

        state.last_seen = now

    def _gc(self) -> None:
        now: float = monotonic()

        if (now - self._last_gc) < self.gc_interval:
            return

        cutoff: float = self.sustained_period * 2
        to_delete: list[str] = [
            ip for ip, s in self._clients.items() if (now - s.last_seen) > cutoff
        ]

        for ip in to_delete:
            del self._clients[ip]

        self._last_gc = now

    def allow(self, ip: str) -> bool:
        state: RateLimitState = self._get_state(ip)

        self._refill(state)
        self._gc()

        if state.burst_tokens < 1:
            return False

        if state.sustained_tokens < 1:
            return False

        state.burst_tokens -= 1
        state.sustained_tokens -= 1

        return True
