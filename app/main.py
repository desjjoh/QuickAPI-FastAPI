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
    try:
        setup_logging()
        await init_db()

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
        try:
            await close_db()
            log.info("Shutdown complete", service=settings.app_name)
        except Exception as e:
            log.error("Error during shutdown", error=str(e))


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
)


app.include_router(items_router)
app.include_router(health_router)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
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
    return {"message": "Hello from FastAPI!"}

import signal

def handle_signal(signum, frame):
    from signal import Signals
    log.info(f"Received {Signals(signum).name}, beginning graceful shutdown", service=settings.app_name)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGQUIT, handle_signal)