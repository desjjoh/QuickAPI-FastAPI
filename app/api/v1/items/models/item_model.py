from pydantic import BaseModel, Field

from app.common.models.base_model import BaseResponse
from app.common.models.price_model import Price


class ItemBase(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Descriptive name of the item (max length 120).",
        examples=["Iron Sword"],
    )

    price: Price = Field(
        ...,
        description="Price from 0.01 through 99999999.99 with at most two decimal places; excess precision is rejected. Accepts numbers or unsigned plain decimal strings; responses are numbers.",
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
