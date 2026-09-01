import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.api_routes import router as api_router
from app.api.system.services.system_service import SystemInfoService
from app.common.docs.openapi import configure_custom_validation_openapi
from app.common.handlers.exception_handler import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.common.handlers.lifecycle_handler import LifecycleHandler
from app.common.middleware.content_type_enforcement import (
    ContentTypeEnforcementASGIMiddleware,
)
from app.common.middleware.cors import CustomCORSASGIMiddleware
from app.common.middleware.method_whitelist import MethodWhitelistASGIMiddleware
from app.common.middleware.prometheus_metrics import PrometheusASGIMiddleware
from app.common.middleware.rate_limit import RateLimitASGIMiddleware
from app.common.middleware.request_body_limit import (
    BodyLimit,
    RequestBodyLimitASGIMiddleware,
)
from app.common.middleware.request_cleanup import RequestCleanupASGIMiddleware
from app.common.middleware.request_context import RequestContextASGIMiddleware
from app.common.middleware.request_header_limit import (
    HeaderLimits,
    RequestHeaderLimitASGIMiddleware,
)
from app.common.middleware.request_header_sanitization import (
    HeaderSanitizationASGIMiddleware,
)
from app.common.middleware.request_logger import RequestLoggingASGIMiddleware
from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware
from app.common.middleware.security_headers import SecurityHeadersMiddleware
from app.config.database import DatabaseService
from app.config.environment import settings
from app.config.logging import log
from app.config.rate_limiter import RateLimiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    name, version, mode = settings.APP_NAME, settings.APP_VERSION, settings.ENV
    pyv: str = sys.version.split()[0]

    try:
        log.info(f"Booting {name} v{version} ({mode}) — Python v{pyv}")

        await app.state.lifecycle.startup()

        port: int = settings.PORT
        log.info(f"HTTP server running on port {port} — http://localhost:{port}")

        yield

    except Exception as exc:
        error_type: str = exc.__class__.__name__
        error_msg: str = getattr(exc, "msg", None) or str(exc).split("\n")[0]

        log.error(f"{error_type} — {error_msg}", exception=exc)

        log.critical('Unhandled fatal error during server runtime — forcing exit')

        raise

    finally:
        log.warning("Shutdown signal received — initiating shutdown")

        await app.state.lifecycle.shutdown()

        log.info("Application exited cleanly")


def create_app() -> FastAPI:
    name: str = settings.APP_NAME
    version: str = settings.APP_VERSION

    started_at = datetime.now(UTC)
    app: FastAPI = FastAPI(
        title=name,
        version=version,
        description="A production-oriented example API built with FastAPI.",
        openapi_tags=[
            {"name": "System", "description": "Runtime and service diagnostics."},
            {"name": "Items", "description": "CRUD operations for items."},
        ],
        lifespan=lifespan,
    )

    app.state.lifecycle = LifecycleHandler()
    app.state.lifecycle.register([DatabaseService()])
    app.state.initialization_timestamp = started_at
    app.state.system_info = SystemInfoService(started_at=started_at)
    app.state.monotonic_start = time.perf_counter()

    app.add_middleware(PrometheusASGIMiddleware)
    app.add_middleware(RequestTimeoutASGIMiddleware)

    app.add_middleware(
        RateLimitASGIMiddleware,
        limiter=RateLimiter(
            max_burst=10,
            burst_window=5,
            max_sustained=100,
            sustained_period=60,
        ),
    )

    app.add_middleware(
        MethodWhitelistASGIMiddleware,
        allowed_methods={"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"},
    )

    app.add_middleware(
        RequestHeaderLimitASGIMiddleware,
        limits=HeaderLimits(
            max_header_count=100,
            max_single_header_bytes=4_096,
            max_total_header_bytes=8_192,
            allow_chunked=False,
        ),
    )

    app.add_middleware(HeaderSanitizationASGIMiddleware)
    app.add_middleware(
        ContentTypeEnforcementASGIMiddleware,
        default_allowed={"application/json", "multipart/form-data"},
        route_overrides=[],
    )

    app.add_middleware(
        RequestBodyLimitASGIMiddleware,
        default_limit=BodyLimit(max_body_bytes=1_048_576),
        route_overrides=[],
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CustomCORSASGIMiddleware,
        origin=["*"],
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        allowed_headers=["content-type", "authorization", "x-requested-with"],
        exposed_headers=['authorization', 'set-cookie'],
        credentials=True,
        max_age=86_400,
    )

    app.add_middleware(RequestLoggingASGIMiddleware)
    app.add_middleware(RequestContextASGIMiddleware)
    app.add_middleware(RequestCleanupASGIMiddleware)

    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(StarletteHTTPException)(http_exception_handler)
    app.exception_handler(Exception)(unhandled_exception_handler)

    app.include_router(api_router)

    configure_custom_validation_openapi(app)

    return app


app: FastAPI = create_app()
