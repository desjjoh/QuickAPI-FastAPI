import time
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import log


class RequestLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration = (time.perf_counter() - start_time) * 1000
            log.error(
                "Unhandled exception during request",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                ms=round(duration, 2),
            )

            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )

        duration = (time.perf_counter() - start_time) * 1000
        log.info(
            "Request completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=round(duration, 2),
        )
        return response
