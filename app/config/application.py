import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp

from app.api.api_routes import create_router
from app.api.system.services.system_service import (
    SystemDiagnosticsService,
    SystemInfoService,
)
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
from app.common.middleware.operational_exposure import OperationalExposureASGIMiddleware
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
from app.common.middleware.request_outcome import RequestOutcomeASGIMiddleware
from app.common.middleware.request_timeout import RequestTimeoutASGIMiddleware
from app.common.middleware.security_headers import SecurityHeadersMiddleware
from app.common.middleware.trusted_proxy import TrustedProxyASGIMiddleware
from app.config.database import DatabaseService
from app.config.environment import settings
from app.config.logging import log
from app.config.rate_limiter import RateLimiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        await app.state.lifecycle.startup()

        port: int = settings.PORT
        log.info(f"HTTP server running on port {port} — http://localhost:{port}")

        yield

    except Exception as exc:
        log.error("Application runtime failed.", error=exc)

        log.critical('Unhandled fatal error during server runtime — forcing exit')

        raise

    finally:
        log.warning("Shutdown signal received — initiating shutdown")

        await app.state.lifecycle.shutdown()

        log.info("Application exited cleanly")


class ObservedFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        return RequestOutcomeASGIMiddleware(
            super().build_middleware_stack(), self.router.routes
        )


def create_app() -> FastAPI:
    name: str = settings.APP_NAME
    version: str = settings.APP_VERSION
    log.info(
        f"Booting {name} v{version} ({settings.ENV}) — Python v{sys.version.split()[0]}"
    )

    started_at = datetime.now(UTC)
    app: FastAPI = ObservedFastAPI(
        docs_url="/docs" if settings.DOCS_ENABLED else None,
        redoc_url="/redoc" if settings.DOCS_ENABLED else None,
        openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
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
    app.state.system_diagnostics = SystemDiagnosticsService(
        lifecycle=app.state.lifecycle,
        started_at=app.state.monotonic_start,
    )

    app.add_middleware(
        OperationalExposureASGIMiddleware,
        docs_enabled=settings.DOCS_ENABLED,
        diagnostics_enabled=settings.DIAGNOSTICS_ENABLED,
        metrics_enabled=settings.METRICS_ENABLED,
    )
    app.add_middleware(
        RequestTimeoutASGIMiddleware,
        first_body_timeout=settings.REQUEST_FIRST_BODY_TIMEOUT_MS / 1000,
        chunk_timeout=settings.REQUEST_CHUNK_TIMEOUT_MS / 1000,
        total_timeout=settings.REQUEST_TIMEOUT_MS / 1000,
    )

    app.add_middleware(
        MethodWhitelistASGIMiddleware,
        allowed_methods=set(settings.HTTP_ALLOWED_METHODS),
    )

    app.add_middleware(
        HeaderSanitizationASGIMiddleware,
        extra_allowed=set(settings.CORS_ALLOWED_HEADERS),
    )
    app.add_middleware(
        ContentTypeEnforcementASGIMiddleware,
        default_allowed=set(settings.HTTP_ALLOWED_CONTENT_TYPES),
        route_overrides=[],
    )

    app.add_middleware(
        RequestBodyLimitASGIMiddleware,
        default_limit=BodyLimit(max_body_bytes=settings.HTTP_MAX_BODY_BYTES),
        route_overrides=[],
    )

    app.add_middleware(
        CustomCORSASGIMiddleware,
        origin=settings.CORS_ORIGINS,
        methods=settings.CORS_METHODS,
        allowed_headers=settings.CORS_ALLOWED_HEADERS,
        exposed_headers=settings.CORS_EXPOSED_HEADERS,
        credentials=settings.CORS_CREDENTIALS,
        max_age=settings.CORS_MAX_AGE_SECONDS,
    )

    app.add_middleware(
        RateLimitASGIMiddleware,
        limiter=RateLimiter(
            window_ms=settings.RATE_LIMIT_WINDOW_MS,
            max_requests=settings.RATE_LIMIT_MAX,
            max_clients=settings.RATE_LIMIT_MAX_CLIENTS,
        ),
    )

    app.add_middleware(SecurityHeadersMiddleware, docs_enabled=settings.DOCS_ENABLED)

    app.add_middleware(
        RequestHeaderLimitASGIMiddleware,
        limits=HeaderLimits(
            max_header_count=settings.HTTP_MAX_HEADER_COUNT,
            max_single_header_bytes=settings.HTTP_MAX_SINGLE_HEADER_BYTES,
            max_total_header_bytes=settings.HTTP_MAX_TOTAL_HEADER_BYTES,
            allow_chunked=False,
        ),
    )

    app.add_middleware(PrometheusASGIMiddleware)
    app.add_middleware(RequestLoggingASGIMiddleware)
    app.add_middleware(RequestContextASGIMiddleware)
    app.add_middleware(
        TrustedProxyASGIMiddleware,
        trusted_proxies=settings.TRUST_PROXY,
        max_header_bytes=settings.HTTP_MAX_SINGLE_HEADER_BYTES,
        max_header_count=settings.HTTP_MAX_HEADER_COUNT,
        max_total_header_bytes=settings.HTTP_MAX_TOTAL_HEADER_BYTES,
    )
    app.add_middleware(RequestCleanupASGIMiddleware)

    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(StarletteHTTPException)(http_exception_handler)
    app.exception_handler(Exception)(unhandled_exception_handler)

    app.include_router(
        create_router(
            diagnostics_enabled=settings.DIAGNOSTICS_ENABLED,
            metrics_enabled=settings.METRICS_ENABLED,
        )
    )

    configure_custom_validation_openapi(app)

    return app


app: FastAPI = create_app()
