from __future__ import annotations

from array import array
from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class RateLimitState:
    timestamps: array[float]
    head: int = 0
    count: int = 0
    expires_at: float = 0.0

    @classmethod
    def new(cls, capacity: int) -> RateLimitState:
        return cls(timestamps=array("d", [0.0]) * capacity)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    status: Literal[429, 503] | None = None
    retry_after_seconds: int = 0


@dataclass(frozen=True, slots=True)
class RateLimitUsage:
    clients: int
    stored_requests: int
    timestamp_slots: int
