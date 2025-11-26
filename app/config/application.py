import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.database import DatabaseService
from app.config.environment import settings
from app.config.logging import log
from app.config.rate_limiter import RateLimiter
from app.controllers.system_controller import router as system_router
from app.docs.openapi import configure_custom_validation_openapi
from app.handlers.exception_handler import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.handlers.lifecycle_handler import lifecycle
from app.middleware.error_logger import ErrorLoggingASGIMiddleware
from app.middleware.rate_limiter import RateLimitASGIMiddleware
from app.middleware.request_cleanup import RequestCleanupASGIMiddleware
from app.middleware.request_context import RequestContextASGIMiddleware
from app.middleware.request_limiter import RequestSizeLimitASGIMiddleware
from app.middleware.request_logger import RequestLoggingASGIMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routes.api_routes import router as api_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    name, version, mode = settings.APP_NAME, settings.APP_VERSION, settings.ENV
    pyv: str = sys.version.split()[0]

    try:
        log.info(f"Booting {name} v{version} ({mode}) — Python v{pyv}")

        lifecycle.register([DatabaseService()])
        await lifecycle.startup()

        port = settings.PORT
        log.info(f"HTTP server running on port {port} — http://localhost:{port}/docs")

        yield
    except Exception as exc:
        error_type: str = exc.__class__.__name__
        error_msg: str = getattr(exc, "msg", None) or str(exc).split("\n")[0]

        log.error(f"{error_type} — {error_msg}", exception=exc)

        log.critical('Unhandled fatal error during server runtime — forcing exit')

        raise
    finally:
        log.warning("Shutdown signal received — initiating shutdown")

        await lifecycle.shutdown()

        log.info("Application exited cleanly")


def create_app() -> FastAPI:
    name: str = settings.APP_NAME
    version: str = settings.APP_VERSION

    app: FastAPI = FastAPI(
        title=name,
        version=version,
        lifespan=lifespan,
    )

    limiter: RateLimiter = RateLimiter(
        max_burst=10,
        burst_window=5,
        max_sustained=100,
        sustained_period=60,
    )

    app.add_middleware(RateLimitASGIMiddleware, limiter=limiter)
    app.add_middleware(RequestSizeLimitASGIMiddleware, max_body_bytes=1_048_576)
    app.add_middleware(RequestContextASGIMiddleware)

    app.add_middleware(ErrorLoggingASGIMiddleware)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingASGIMiddleware)

    app.add_middleware(RequestCleanupASGIMiddleware)

    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(StarletteHTTPException)(http_exception_handler)
    app.exception_handler(Exception)(unhandled_exception_handler)

    app.include_router(system_router)
    app.include_router(api_router)

    configure_custom_validation_openapi(app)

    return app


app: FastAPI = create_app()
