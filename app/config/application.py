import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.api_routes import router as api_router
from app.common.docs.openapi import configure_custom_validation_openapi
from app.common.handlers.exception_handler import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.common.handlers.lifecycle_handler import lifecycle
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
from app.system.controllers.system_controller import router as system_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    name, version, mode = settings.APP_NAME, settings.APP_VERSION, settings.ENV
    pyv: str = sys.version.split()[0]

    try:
        log.info(f"Booting {name} v{version} ({mode}) — Python v{pyv}")

        lifecycle.register([DatabaseService()])
        await lifecycle.startup()

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

    app.include_router(system_router)
    app.include_router(api_router)

    configure_custom_validation_openapi(app)

    return app


app: FastAPI = create_app()
