from collections.abc import AsyncGenerator

import httpx
import pytest_asyncio
from fastapi import FastAPI

from app.config.application import create_app


@pytest_asyncio.fixture
async def app() -> AsyncGenerator[FastAPI, None]:
    """Start the complete application, including its production lifespan services."""
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
