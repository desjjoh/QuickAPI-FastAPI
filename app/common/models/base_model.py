from datetime import UTC, datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.common.models.parameters_model import ENTITY_ID_PATTERN


class BaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, serialize_by_alias=True)

    id: str = Field(
        ...,
        min_length=16,
        max_length=16,
        pattern=ENTITY_ID_PATTERN,
        description="Globally unique identifier of the entity (16 ASCII letters or digits).",
        examples=['A1b2C3d4E5f6G7h8'],
    )

    created_at: datetime = Field(
        ...,
        validation_alias=AliasChoices('createdAt', 'created_at'),
        serialization_alias='createdAt',
        description="Timestamp when the entity was first created (UTC).",
        examples=[datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC).isoformat()],
    )

    updated_at: datetime = Field(
        ...,
        validation_alias=AliasChoices('updatedAt', 'updated_at'),
        serialization_alias='updatedAt',
        description="Timestamp of the most recent update to the entity (UTC).",
        examples=[datetime(2025, 1, 1, 12, 5, 0, tzinfo=UTC).isoformat()],
    )
