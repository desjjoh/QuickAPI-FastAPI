"""
main.py
--------
Application entrypoint for the FastAPI service.

Handles:
    - Application startup and graceful shutdown via lifespan context.
    - Structured logging initialization.
    - Database connection management.
    - Exception handling and route registration.

This module follows the same design philosophy as the Express and NestJS
services — modular, observable, and fault-tolerant.

✅ Fail fast on startup failure.
✅ Leave a trail through structured contextual logs.
✅ Shutdown gracefully with explicit cleanup.

"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.items.routes import router as items_router
from app.api.health.routes import router as health_router

from app.core.config import settings
from app.core.logging import setup_logging, log
from app.core.middleware import RequestLoggingMiddleware
from app.services.db import init_db, close_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Application lifespan context.

    Handles initialization and teardown of critical resources such as
    logging and database connections. Ensures clean startup and shutdown.

    Args:
        _: FastAPI
            The FastAPI application instance (unused).

    Yields:
        None
            Control back to FastAPI once startup tasks are complete.

    Raises:
        Exception:
            If initialization fails, logs the error and re-raises.
    """
    try:
        setup_logging()
        await init_db()

        # Log startup messages
        log.info(
            (
                f"Server running in development mode at http://localhost:8000"
                if settings.debug
                else f"Server running in production mode at http://localhost:8000"
            ),
            service=settings.app_name,
            port=8000,
        )

        log.info(
            "Swagger docs available at http://localhost:8000/docs",
            url="http://localhost:8000/docs",
            service=settings.app_name,
        )

        yield

    except Exception as e:
        log.error("Startup failed", error=str(e))
        raise

    finally:
        # Graceful shutdown
        try:
            await close_db()
            log.info("Shutdown complete", service=settings.app_name)
        except Exception as e:
            log.error("Error during shutdown", error=str(e))


# Instantiate FastAPI with managed lifespan
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
)


# Register routes and middleware
app.include_router(items_router)
app.include_router(health_router)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    Global exception handler for Starlette HTTP exceptions.

    Logs the exception with request context and returns a JSON response
    containing the HTTP status and message.

    Args:
        request: Request
            The incoming FastAPI request object.
        exc: StarletteHTTPException
            The raised exception instance.

    Returns:
        JSONResponse:
            Formatted response with `status_code` and `detail`.
    """
    log.warning(
        "HTTP exception raised",
        method=request.method,
        path=request.url.path,
        status=exc.status_code,
        detail=str(exc.detail or "No detail provided"),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    """
    Root endpoint.

    Returns a simple health message indicating the service is reachable.

    Returns:
        dict[str, str]:
            JSON object containing a simple greeting.
    """
    return {"message": "Hello from FastAPI!"}

import signal

import signal

def handle_signal(signum, frame):
    from signal import Signals
    log.info(f"Received {Signals(signum).name}, beginning graceful shutdown", service=settings.app_name)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGQUIT, handle_signal)