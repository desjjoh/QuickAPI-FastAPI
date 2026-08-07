import os
import socket

import httpx
import pytest

from app.config.environment import settings

pytestmark = pytest.mark.e2e


async def test_info_uses_settings_and_current_process_metadata(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "APP_NAME", "Controlled API")
    monkeypatch.setattr(settings, "APP_VERSION", "9.8.7")
    monkeypatch.setattr(settings, "ENV", "test")

    response = await client.get("/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Controlled API",
        "version": "9.8.7",
        "environment": "test",
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
    }
