import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.database import DatabaseService
from app.config.environment import settings
from app.config.logging import log
from app.controllers.system_controller import router as system_router
from app.handlers.exception_handler import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.handlers.lifecycle_handler import lifecycle
from app.middleware.request_context import RequestContextASGIMiddleware
from app.middleware.request_logger import RequestLoggingASGIMiddleware
from app.routes.api_routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    name, version, mode = settings.APP_NAME, settings.APP_VERSION, settings.ENV
    pyv = sys.version.split()[0]

    log.info(f"Booting {name} v{version} ({mode}) — Python v{pyv}")

    try:
        lifecycle.register([DatabaseService()])
        await lifecycle.startup()

        port = settings.PORT
        log.info(f"HTTP server running on port {port} — http://localhost:{port}/docs")

        yield
    except Exception:
        log.critical('Unhandled fatal error during server runtime')

        raise
    finally:
        log.warning("Shutdown signal received — beginning shutdown")

        await lifecycle.shutdown()

        log.info("Application exited cleanly")


def create_app() -> FastAPI:
    name = settings.APP_NAME
    version = settings.APP_VERSION

    app = FastAPI(
        title=name,
        version=version,
        lifespan=lifespan,
    )

    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(StarletteHTTPException)(http_exception_handler)
    app.exception_handler(Exception)(unhandled_exception_handler)

    app.add_middleware(RequestContextASGIMiddleware)
    app.add_middleware(RequestLoggingASGIMiddleware)

    app.include_router(system_router)
    app.include_router(api_router)

    return app


app = create_app()
