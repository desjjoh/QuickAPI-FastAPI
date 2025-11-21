from datetime import UTC, datetime

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": exc.status_code,
            "message": exc.detail,
            "timestamp": _now(),
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    status = 500
    detail = "Internal server error"
    return JSONResponse(
        status_code=status,
        content={
            "status": status,
            "message": detail,
            "timestamp": _now(),
        },
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    status = 422
    return JSONResponse(
        status_code=status,
        content={
            "status": status,
            "message": exc.errors(),
            "timestamp": _now(),
        },
    )
