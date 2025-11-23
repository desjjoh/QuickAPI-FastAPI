from pydantic import Field

from app.models.base_model import BaseResponse


class ItemResponse(BaseResponse):
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


class CreateItemRequest(ItemResponse):
    pass
