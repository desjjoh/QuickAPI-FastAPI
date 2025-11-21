from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

SEMVER_REGEX = r"^\d+\.\d+\.\d+$"


class RootResponse(BaseModel):
    message: str = Field(
        ...,
        description="A friendly greeting from the API",
        examples=["Hello World! Welcome to FastAPI!"],
    )


class HealthResponse(BaseModel):
    alive: bool = Field(
        ...,
        description="Whether the server is currently alive.",
        examples=[True],
    )
    uptime: float = Field(
        ...,
        description="Server uptime in seconds.",
        examples=[123.45],
    )
    timestamp: str = Field(
        ...,
        description="Current server timestamp in ISO-8601 format.",
        examples=["2025-08-14T12:00:00Z"],
    )


class ReadyResponse(BaseModel):
    ready: bool = Field(
        ...,
        description="Whether the system is currently ready.",
        examples=[True],
    )


class InfoResponse(BaseModel):
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
        description="Process ID.",
        examples=[12345],
    )


class SystemResponse(BaseModel):
    uptime_s: float = Field(
        ...,
        description="Application uptime in seconds.",
        examples=[123.45],
    )
    timestamp: int = Field(
        ...,
        description="Current timestamp in milliseconds since Unix epoch.",
        examples=[1_732_133_579_791],
    )
    event_loop_lag_ms: float = Field(
        ...,
        description="Approximate event loop lag in milliseconds.",
        examples=[3.21],
    )
    db: Literal["connected", "disconnected"] = Field(
        ...,
        description="Database connectivity status.",
        examples=["connected"],
    )
