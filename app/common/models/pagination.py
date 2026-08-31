from collections.abc import Sequence
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field

T = TypeVar("T")


class PaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number", examples=[1])

    limit: int = Field(
        default=20, ge=1, le=100, description="Items per page", examples=[20]
    )

    order: Literal["asc", "desc"] = Field(
        default="asc", description="Sort direction", examples=["asc"]
    )

    search: str | None = Field(
        default=None,
        description="Optional search term applied to item names",
        examples=["sword"],
    )

    @computed_field(return_type=int)  # type: ignore[prop-decorator]
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit

    model_config = {"frozen": True}


class PaginatedResult[T](BaseModel):
    model_config = ConfigDict(frozen=True)

    data: Sequence[T] = Field(
        ..., description="The list of items returned for this page."
    )

    total: int = Field(
        ...,
        description="Total number of items matching the query.",
        examples=[125],
    )

    page: int = Field(
        ...,
        description="The current page number (1-indexed).",
        examples=[1],
    )

    limit: int = Field(
        ...,
        description="Maximum number of items per page.",
        examples=[20],
    )

    @property
    def total_pages(self) -> int:
        if self.limit == 0:
            return 1
        return max((self.total + self.limit - 1) // self.limit, 1)
