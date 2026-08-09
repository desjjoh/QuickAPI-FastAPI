from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.config.application import create_app


@pytest.fixture
def error_app() -> FastAPI:
    return create_app()


@pytest.fixture
async def error_client(error_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=error_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client
