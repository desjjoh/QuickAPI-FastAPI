from pydantic import BaseModel, Field


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
