from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReadyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    status: Literal["up", "down"]
    response_time_ms: float = Field(..., ge=0)


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool = Field(
        ...,
        description="Whether the system is currently ready.",
        examples=[True],
    )
    status: Literal["ready", "not_ready"]
    timestamp: datetime
    checks: list[ReadyCheck]

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        if self.timestamp.utcoffset() != UTC.utcoffset(self.timestamp):
            raise ValueError("timestamp must be timezone-aware UTC")
        expected = "ready" if self.ready else "not_ready"
        if self.status != expected:
            raise ValueError("ready and status contradict each other")
        if self.ready and any(check.status == "down" for check in self.checks):
            raise ValueError("a ready response cannot contain a down check")
        return self

    @classmethod
    def from_state(
        cls, *, ready: bool, checks: list[ReadyCheck], timestamp: datetime | None = None
    ) -> Self:
        return cls(
            ready=ready,
            status="ready" if ready else "not_ready",
            timestamp=timestamp or datetime.now(UTC),
            checks=checks,
        )
