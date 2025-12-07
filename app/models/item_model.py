from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from app.models.base_model import BaseResponse
from app.models.pagination import PaginationQuery


class ItemBase(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Descriptive name of the item (max length 120).",
        examples=["Iron Sword"],
    )

    price: float = Field(
        ...,
        ge=0,
        description="Price of the item represented as a decimal with 2 fractional digits.",
        examples=[49.99],
    )

    description: str | None = Field(
        None,
        max_length=500,
        description="Optional free-text description of the item; null when not provided.",
        examples=["A finely crafted steel blade."],
    )


class ItemResponse(ItemBase, BaseResponse):
    pass


class UpdateItemRequest(BaseModel):
    name: str | SkipJsonSchema[None] = Field(
        None,
        min_length=1,
        max_length=120,
        description="Descriptive name of the item (max length 120).",
        examples=["Iron Sword"],
    )

    price: float | SkipJsonSchema[None] = Field(
        None,
        ge=0,
        description="Price of the item represented as a decimal with 2 fractional digits.",
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
    def reject_explicit_nulls(cls, value: Any):
        if value is None:
            raise PydanticCustomError(
                "null_forbidden",
                "Field cannot be null (omit the field to skip updating it)",
            )

        return value

    @model_validator(mode="after")
    def reject_empty_payload(self):
        provided = {k: v for k, v in self.model_dump(exclude_unset=True).items()}

        if not provided:
            raise PydanticCustomError(
                "empty_body", "At least one field must be provided"
            )

        return self


class ItemPaginationQuery(PaginationQuery):
    sort: Literal["name", "price", "created_at"] = Field(
        "price", description="Field to sort items by", examples=["price"]
    )

    min_price: float | None = Field(
        None, ge=0, description="Minimum price filter", examples=[50.00]
    )
    max_price: float | None = Field(
        None, ge=0, description="Maximum price filter", examples=[100.00]
    )

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price cannot exceed max_price.")

        return self
