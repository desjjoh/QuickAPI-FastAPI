from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    status: int = Field(..., description="HTTP status code", examples=[503])
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Application not ready"],
    )
    timestamp: str = Field(
        ..., description="ISO8601 timestamp", examples=["2025-08-14T12:00:00Z"]
    )
