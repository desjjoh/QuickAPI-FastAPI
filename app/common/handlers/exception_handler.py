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

    log.error(exc.detail)
    return error_response(status=exc.status_code, message=exc.detail)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
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

    log.error(message)
    return error_response(status=status_code, message=message)


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = "Internal server error."

    log.error(message)
    return error_response(status=status_code, message=message)
