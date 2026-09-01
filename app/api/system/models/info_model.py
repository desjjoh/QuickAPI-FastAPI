from datetime import UTC, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SEMVER_REGEX = r"^\d+\.\d+\.\d+$"


class InfoResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(
        ...,
        description="Application name.",
        examples=["quickapi"],
    )

    version: Annotated[str, StringConstraints(pattern=SEMVER_REGEX)] = Field(
        ...,
        description="Application semantic version.",
        examples=["1.0.0"],
    )

    environment: Literal["development", "production", "test"] = Field(
        ...,
        description="Current environment mode.",
        examples=["development"],
    )

    hostname: str = Field(
        ...,
        description="Server hostname.",
        examples=["server-001"],
    )

    pid: int = Field(
        ...,
        gt=0,
        description="Process ID.",
        examples=[12345],
    )

    python_version: str = Field(
        ..., min_length=1, description="Running Python version.", examples=["3.12.1"]
    )
    platform: str = Field(
        ..., min_length=1, description="Operating system platform.", examples=["Linux"]
    )
    architecture: str = Field(
        ..., min_length=1, description="Machine architecture.", examples=["x86_64"]
    )
    started_at: datetime = Field(
        ..., description="Application creation time as a timezone-aware UTC timestamp."
    )
    timezone: str = Field(
        ..., min_length=1, description="Configured IANA timezone identifier."
    )

    @field_validator("started_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("started_at must be timezone-aware and in UTC")
        return value

    @field_validator("timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA identifier") from exc
        return value
