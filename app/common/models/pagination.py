from collections.abc import Sequence
from typing import Annotated, Literal, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    WithJsonSchema,
    computed_field,
    field_validator,
    model_validator,
)

MAX_SAFE_INTEGER = 9007199254740991


T = TypeVar("T")


class PaginationQuery(BaseModel):
    page: int = Field(
        default=1, ge=1, le=MAX_SAFE_INTEGER, description="Page number", examples=[1]
    )

    limit: int = Field(
        default=25, ge=1, le=100, description="Items per page", examples=[25]
    )

    order: Annotated[
        Literal['asc', 'desc'],
        WithJsonSchema(
            {'type': 'string', 'pattern': '^([Aa][Ss][Cc]|[Dd][Ee][Ss][Cc])$'},
            mode='validation',
        ),
    ] = Field(
        default="asc",
        description="Case-insensitive ASC or DESC; normalized internally",
        examples=["ASC"],
    )

    search: str | None = Field(
        default=None,
        description="Optional search term applied to item names",
        examples=["sword"],
    )

    @field_validator('order', mode='before')
    @classmethod
    def normalize_order(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode='after')
    def validate_offset(self) -> Self:
        if self.offset > MAX_SAFE_INTEGER:
            raise ValueError('Pagination offset exceeds the maximum safe integer')

        return self

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
