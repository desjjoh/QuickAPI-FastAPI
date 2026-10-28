from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool = Field(
        ...,
        description="Whether the system is currently ready.",
        examples=[True],
    )
    status: Literal["ready", "not_ready"]
    timestamp: datetime

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        if self.timestamp.utcoffset() != UTC.utcoffset(self.timestamp):
            raise ValueError("timestamp must be timezone-aware UTC")
        expected = "ready" if self.ready else "not_ready"
        if self.status != expected:
            raise ValueError("ready and status contradict each other")
        return self

    @classmethod
    def from_state(cls, *, ready: bool, timestamp: datetime | None = None) -> Self:
        return cls(
            ready=ready,
            status="ready" if ready else "not_ready",
            timestamp=timestamp or datetime.now(UTC),
        )
