from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from app.common.models.converter import model_to

pytestmark = pytest.mark.unit


class Source(BaseModel):
    value: int
    optional: str | None = None


@dataclass
class Target:
    value: int


def test_converts_to_typed_target_with_dump_options() -> None:
    result = model_to(Target, Source(value=3), exclude_none=True)
    assert result == Target(value=3)
    assert isinstance(result, Target)


def test_conversion_validation_failure_names_target_without_leaking_details() -> None:
    class NamedTarget(BaseModel):
        required: str

    with pytest.raises(HTTPException) as caught:
        model_to(NamedTarget, Source(value=3))
    assert caught.value.status_code == 500
    assert caught.value.detail == "Internal model conversion failed for 'NamedTarget'."
    assert "required" not in caught.value.detail


def test_conversion_uses_string_name_for_unnamed_target() -> None:
    with pytest.raises(HTTPException) as caught:
        model_to(list[int], Source(value=3))
    assert "'list'" in caught.value.detail
