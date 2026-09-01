from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    alive: bool = Field(
        ...,
        description="Whether the server is currently alive.",
        examples=[True],
    )

    status: Literal["alive", "dead"] = Field(
        ...,
        description="Process status derived from whether the server is alive.",
        examples=["alive"],
    )

    uptime: float = Field(
        ...,
        ge=0,
        description="Server uptime in seconds.",
        examples=[123.45],
    )

    timestamp: datetime = Field(
        ...,
        description="Current timezone-aware UTC server timestamp.",
        examples=[datetime(2025, 8, 14, 12, tzinfo=UTC)],
    )

    @model_validator(mode="after")
    def validate_health_state(self) -> Self:
        expected_status: Literal["alive", "dead"] = "alive" if self.alive else "dead"
        if self.status != expected_status:
            raise ValueError("status must correspond to alive")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware and in UTC")
        return self

    @classmethod
    def from_alive(
        cls,
        *,
        alive: bool,
        uptime: float,
        timestamp: datetime,
    ) -> Self:
        return cls(
            alive=alive,
            status="alive" if alive else "dead",
            uptime=uptime,
            timestamp=timestamp,
        )
