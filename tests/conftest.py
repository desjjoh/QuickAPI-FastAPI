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
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "METRICS_API_KEY": "test-metrics-key",
    }
)

import pytest
import structlog
from fastapi import FastAPI

from app.common.handlers.lifecycle_handler import LifecycleHandler
from app.common.store.request_context import RequestContext
from app.config.metrics import REQUEST_COUNT, REQUEST_LATENCY


@pytest.fixture(autouse=True)
def reset_process_state() -> Iterator[None]:
    """Isolate process-wide observability and request state for every test."""
    REQUEST_COUNT.clear()
    REQUEST_LATENCY.clear()
    RequestContext.clear()
    structlog.contextvars.clear_contextvars()
    yield
    REQUEST_COUNT.clear()
    REQUEST_LATENCY.clear()
    RequestContext.clear()
    structlog.contextvars.clear_contextvars()


@pytest.fixture
def lightweight_app() -> FastAPI:
    """Provide a lifecycle-free app for unit tests that replace dependencies."""
    application = FastAPI()
    application.state.lifecycle = LifecycleHandler()
    return application
