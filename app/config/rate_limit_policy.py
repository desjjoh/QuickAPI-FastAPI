"""Shared bounds for env configuration and direct limiter construction."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_TIMESTAMP_SLOTS = 2_000_000
DEFAULT_WINDOW_MS = 60_000
DEFAULT_MAX_REQUESTS = 200
DEFAULT_MAX_CLIENTS = 10_000
WindowMilliseconds = Annotated[int, Field(ge=1, le=86_400_000)]
RequestCapacity = Annotated[int, Field(ge=1, le=10_000)]
ClientCapacity = Annotated[int, Field(ge=1, le=100_000)]


class RateLimitPolicy(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, validate_default=True)
    window_ms: WindowMilliseconds = DEFAULT_WINDOW_MS
    max_requests: RequestCapacity = DEFAULT_MAX_REQUESTS
    max_clients: ClientCapacity = DEFAULT_MAX_CLIENTS

    @model_validator(mode="after")
    def validate_storage(self) -> Self:
        if self.max_requests * self.max_clients > MAX_TIMESTAMP_SLOTS:
            raise ValueError(
                f"rate limiter storage must not exceed {MAX_TIMESTAMP_SLOTS} timestamp slots"
            )

        return self
