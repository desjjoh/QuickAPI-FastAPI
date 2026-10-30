from typing import Any, Self

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from app.common.models.price_model import Price
from app.common.models.version_model import VersionInput


class UpdateItemRequest(VersionInput):
    name: str | SkipJsonSchema[None] = Field(
        None,
        min_length=1,
        max_length=120,
        description="Descriptive name of the item (max length 120).",
        examples=["Iron Sword"],
    )

    price: Price | SkipJsonSchema[None] = Field(
        None,
        description="Price from 0.01 through 99999999.99 with at most two decimal places; numbers or unsigned plain decimal strings. Excess precision is rejected.",
        examples=[49.99],
    )

    description: str | None = Field(
        None,
        max_length=500,
        description="Optional free-text description of the item; null when not provided.",
        examples=["A finely crafted steel blade."],
    )

    @field_validator("name", "price", mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: Any) -> Any:
        if value is None:
            raise PydanticCustomError(
                "null_forbidden",
                "Field cannot be null (omit the field to skip updating it)",
            )

        return value

    @model_validator(mode="after")
    def reject_empty_payload(self) -> Self:
        provided = {k: v for k, v in self.model_dump(exclude_unset=True).items()}

        if not provided.keys() - {'expected_version'}:
            raise PydanticCustomError(
                "empty_body", "At least one field must be provided"
            )

        return self
