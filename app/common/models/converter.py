from __future__ import annotations

from collections.abc import Hashable
from functools import lru_cache
from typing import Any, TypeVar, cast

from fastapi import HTTPException
from pydantic import BaseModel, TypeAdapter
from pydantic_core import ValidationError

T = TypeVar("T")


@lru_cache(maxsize=256)
def _adapter(tp: Hashable) -> TypeAdapter[Any]:
    return TypeAdapter(tp)


def model_to[T](tp: type[T], model: BaseModel, **dump_kwargs: Any) -> T:
    target = getattr(tp, "__name__", str(tp))

    try:
        data = model.model_dump(**dump_kwargs)
        return cast(T, _adapter(cast(Hashable, tp)).validate_python(data))
    except ValidationError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal model conversion failed for '{target}'.",
        ) from e
