from datetime import UTC, datetime
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    status: int = Field(
        ..., description="HTTP status code", examples=[status.HTTP_418_IM_A_TEAPOT]
    )

    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["I'm a teapot."],
    )

    timestamp: int = Field(
        ...,
        description="Unix timestamp in milliseconds.",
        examples=[1_764_281_029],
    )


def error_response(
    status: int,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    ts_ms: int = int(datetime.now(UTC).timestamp() * 1_000)

    model: ErrorResponse = ErrorResponse(
        status=status,
        message=message,
        timestamp=ts_ms,
    )

    return JSONResponse(
        status_code=status,
        content=model.model_dump(),
        headers=headers or {},
    )


class ModelConversionError(RuntimeError):
    def __init__(
        self, *, target: str, errors: list[dict[str, Any]], source: str | None = None
    ):
        self.target = target
        self.errors = errors
        self.source = source
        msg = f"Failed to convert model to {target}"

        if source:
            msg = f"{msg} (source={source})"

        super().__init__(msg)
