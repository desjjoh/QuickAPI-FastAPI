from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from app.config.application import create_app, lifespan

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_app_factory_isolated_and_lifespan_starts_and_stops() -> None:
    first, second = create_app(), create_app()
    assert first is not second
    assert first.state.lifecycle is not second.state.lifecycle
    first.state.lifecycle.startup = AsyncMock()
    first.state.lifecycle.shutdown = AsyncMock()
    async with lifespan(first):
        first.state.lifecycle.startup.assert_awaited_once()
    first.state.lifecycle.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_still_shuts_down_after_startup_error() -> None:
    app = FastAPI()
    lifecycle = create_app().state.lifecycle
    lifecycle.startup = AsyncMock(side_effect=RuntimeError("boom"))
    lifecycle.shutdown = AsyncMock()
    app.state.lifecycle = lifecycle
    with pytest.raises(RuntimeError, match="boom"):
        async with lifespan(app):
            pass
    app.state.lifecycle.shutdown.assert_awaited_once()
