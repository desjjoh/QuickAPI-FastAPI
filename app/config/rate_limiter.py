from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import Literal

from app.common.store.rate_limit import (
    RateLimitDecision,
    RateLimitState,
    RateLimitUsage,
)
from app.config.rate_limit_policy import (
    DEFAULT_MAX_CLIENTS,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_WINDOW_MS,
    RateLimitPolicy,
)


class RateLimiter:
    """One bounded rolling-window store per instance, with atomic local admission."""

    def __init__(
        self,
        window_ms: int = DEFAULT_WINDOW_MS,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        max_clients: int = DEFAULT_MAX_CLIENTS,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.policy = RateLimitPolicy(
            window_ms=window_ms, max_requests=max_requests, max_clients=max_clients
        )
        # An injected clock uses monotonic milliseconds, matching the public policy.
        self._now = clock if clock is not None else lambda: monotonic() * 1000
        self._clients: OrderedDict[bytes, RateLimitState] = OrderedDict()
        self._stored_requests = 0
        self._lock = Lock()

    @property
    def usage(self) -> RateLimitUsage:
        with self._lock:
            return RateLimitUsage(
                len(self._clients),
                self._stored_requests,
                len(self._clients) * self.policy.max_requests,
            )

    def admit(self, identity: str) -> RateLimitDecision:
        # Resolve identity before calling us; never reinterpret forwarding here.
        key = hashlib.sha256(identity.encode("utf-8")).digest()

        with self._lock:
            now = self._now()

            self._expire_clients(now)
            client = self._clients.get(key)

            if client is None:
                if len(self._clients) >= self.policy.max_clients:
                    earliest = next(iter(self._clients.values()))

                    return self._reject(503, earliest.expires_at, now)

                client = RateLimitState.new(self.policy.max_requests)

            cutoff = now - self.policy.window_ms

            while client.count and client.timestamps[client.head] <= cutoff:
                client.head = (client.head + 1) % self.policy.max_requests
                client.count -= 1
                self._stored_requests -= 1

            if client.count == self.policy.max_requests:
                return self._reject(
                    429, client.timestamps[client.head] + self.policy.window_ms, now
                )

            tail = (client.head + client.count) % self.policy.max_requests
            client.timestamps[tail] = now
            client.count += 1
            client.expires_at = now + self.policy.window_ms
            self._stored_requests += 1
            self._clients[key] = client

            # Equal windows and a monotonic clock order clients by next expiry.
            # Rejections never move an entry or extend its expiry.
            self._clients.move_to_end(key)

            return RateLimitDecision(allowed=True)

    def _expire_clients(self, now: float) -> None:
        while self._clients:
            key, client = next(iter(self._clients.items()))

            if client.expires_at > now:
                break

            del self._clients[key]
            self._stored_requests -= client.count

    @staticmethod
    def _reject(
        status: Literal[429, 503], available_at: float, now: float
    ) -> RateLimitDecision:
        return RateLimitDecision(
            False, status, max(1, math.ceil((available_at - now) / 1000))
        )
