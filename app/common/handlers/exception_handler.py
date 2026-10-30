import json
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.models.error_model import error_response
from app.config.logging import log


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:

    if exc.status_code < 500:
        log.warning("HTTP request rejected.", status=exc.status_code)
    else:
        log.error("HTTP request failed.", status=exc.status_code, error=exc)

    return error_response(
        status=exc.status_code,
        message=_detail_message(exc.detail),
        headers=exc.headers,
    )


def _detail_message(detail: Any) -> str:
    """Render every shape accepted by HTTPException without changing the envelope."""
    if isinstance(detail, str):
        return detail

    return json.dumps(detail, separators=(",", ":"), sort_keys=True, default=str)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    if any(error['type'] == 'json_invalid' for error in exc.errors()):
        log.warning("HTTP request rejected.", status=400)

        return error_response(status=400, message="Malformed JSON request body.")

    status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT
    parts: list[str] = []

    for error in exc.errors():
        loc = error["loc"]
        msg: str = error["msg"]

        loc_parts: list[str] = [str(p) for p in loc]
        field_path: str = ".".join(loc_parts)

        if field_path:
            parts.append(f"{field_path} → {msg}")

        else:
            parts.append(msg)

    message: str = "Validation failed: " + "; ".join(parts) + '.'

    log.warning("HTTP request rejected.", status=status_code)

    return error_response(status=status_code, message=message)


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = "Internal Server Error"

    log.error(
        "HTTP request failed.",
        status=status_code,
        error=exc,
        requestId=request.scope.get("ctx", {}).get("request_id"),
    )

    return error_response(status=status_code, message=message)
