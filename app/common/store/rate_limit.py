from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass
class RateLimitState:
    burst_tokens: float
    sustained_tokens: float
    last_burst_reset: float
    last_refill: float
    last_seen: float

    @classmethod
    def new(cls, max_burst: int, max_sustained: int) -> RateLimitState:
        now = monotonic()
        return cls(
            burst_tokens=max_burst,
            sustained_tokens=max_sustained,
            last_burst_reset=now,
            last_refill=now,
            last_seen=now,
        )
