"""Strict item revision preconditions shared by mutation models."""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

MAX_VERSION = 4294967295


def normalize_revision_number(value: object) -> object:
    # JSON has one number type in Express; 1.0 and 1 are the same revision.
    if isinstance(value, float) and value.is_integer():
        return int(value)

    return value


Version = Annotated[
    int,
    BeforeValidator(normalize_revision_number),
    Field(strict=True, ge=1, le=MAX_VERSION),
]


class VersionInput(BaseModel):
    expected_version: Version
