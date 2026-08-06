from typing import Literal

from pydantic import Field, model_validator

from app.common.models.pagination import PaginationQuery


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
