import io
from unittest.mock import AsyncMock

import pytest

from app.config import application
from app.config.logging import create_logger

pytestmark = pytest.mark.e2e


async def test_boot_banner_precedes_registration_and_service_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    logger = create_logger(production=False, level="DEBUG", stream=output)
    monkeypatch.setattr(application, "log", logger)
    monkeypatch.setattr("app.common.handlers.lifecycle_handler.log", logger)
    start, stop = AsyncMock(), AsyncMock()
    monkeypatch.setattr(application.DatabaseService, "start", start)
    monkeypatch.setattr(application.DatabaseService, "stop", stop)

    app = application.create_app()
    construction = output.getvalue()
    assert construction.count("Booting ") == 1
    assert construction.index("Booting ") < construction.index(
        "Registering lifecycle services"
    )
    start.assert_not_awaited()

    async with app.router.lifespan_context(app):
        lines = output.getvalue()
        assert lines.count("Booting ") == 1
        assert (
            lines.index("Lifecycle registration completed")
            < lines.index("Starting services")
            < lines.index("Service started")
            < lines.index("HTTP server running")
        )
        start.assert_awaited_once()
    stop.assert_awaited_once()
