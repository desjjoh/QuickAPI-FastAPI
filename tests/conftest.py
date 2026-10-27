import os
from collections.abc import Iterator

# Do not allow a developer shell or CI runner to alter collection-time settings.
os.environ.update(
    {
        "APP_NAME": "QuickAPI",
        "APP_VERSION": "1.0.0",
        "ENV": "test",
        "LOG_LEVEL": "ERROR",
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "API_PUBLISHED_PORT": "8000",
        "MYSQL_PUBLISHED_PORT": "3308",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "CORS_ORIGINS": "http://localhost:3000,https://client.test,https://client.example",
        "CORS_METHODS": "GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS",
        "CORS_ALLOWED_HEADERS": "content-type,authorization,x-requested-with",
        "CORS_EXPOSED_HEADERS": "authorization,set-cookie",
        "CORS_CREDENTIALS": "true",
        "CORS_MAX_AGE_SECONDS": "86400",
        "TRUST_PROXY": "",
        "REQUEST_TIMEOUT_MS": "10000",
        "REQUEST_FIRST_BODY_TIMEOUT_MS": "5000",
        "REQUEST_CHUNK_TIMEOUT_MS": "2000",
        "HTTP_MAX_BODY_BYTES": "1048576",
        "HTTP_MAX_HEADER_COUNT": "100",
        "HTTP_MAX_SINGLE_HEADER_BYTES": "4096",
        "HTTP_MAX_TOTAL_HEADER_BYTES": "8192",
        "HTTP_ALLOWED_METHODS": "GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS",
        "HTTP_ALLOWED_CONTENT_TYPES": "application/json,multipart/form-data",
    }
)

import pytest
import structlog
from fastapi import FastAPI

from app.common.handlers.lifecycle_handler import LifecycleHandler
from app.common.store.request_context import RequestContext
from app.config.metrics import REQUEST_ABORTED, REQUEST_COUNT, REQUEST_DURATION


@pytest.fixture(autouse=True)
def reset_process_state() -> Iterator[None]:
    """Isolate process-wide observability and request state for every test."""
    REQUEST_COUNT.clear()
    REQUEST_DURATION.clear()
    REQUEST_ABORTED.clear()
    RequestContext.clear()
    structlog.contextvars.clear_contextvars()
    yield
    REQUEST_COUNT.clear()
    REQUEST_DURATION.clear()
    REQUEST_ABORTED.clear()
    RequestContext.clear()
    structlog.contextvars.clear_contextvars()


@pytest.fixture
def lightweight_app() -> FastAPI:
    """Provide a lifecycle-free app for unit tests that replace dependencies."""
    application = FastAPI()
    application.state.lifecycle = LifecycleHandler()
    return application
