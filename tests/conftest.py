import os

os.environ.setdefault("APP_NAME", "QuickAPI")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
from fastapi import FastAPI

from app.common.handlers.lifecycle_handler import LifecycleHandler


@pytest.fixture
def lightweight_app() -> FastAPI:
    """Provide a lifecycle-free app for unit tests that replace dependencies."""
    application = FastAPI()
    application.state.lifecycle = LifecycleHandler()
    return application
