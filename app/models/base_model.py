from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    id: str = Field(
        ...,
        min_length=16,
        max_length=16,
        description="Globally unique identifier of the entity (16-character hex).",
        examples=[uuid4().hex[:16]],
    )

    created_at: datetime = Field(
        ...,
        description="Timestamp when the entity was first created (UTC).",
        examples=[datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC).isoformat()],
    )

    updated_at: datetime = Field(
        ...,
        description="Timestamp of the most recent update to the entity (UTC).",
        examples=[datetime(2025, 1, 1, 12, 5, 0, tzinfo=UTC).isoformat()],
    )

    class Config:
        from_attributes = True
