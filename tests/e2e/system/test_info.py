import os
import platform
import re
import socket
from datetime import UTC, datetime

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
    monkeypatch.setattr(settings, "TIMEZONE", "Etc/UTC")

    response = await client.get("/info")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "name",
        "version",
        "environment",
        "hostname",
        "pid",
        "python_version",
        "platform",
        "architecture",
        "started_at",
        "timezone",
    }
    assert payload["name"] == "Controlled API"
    assert re.fullmatch(r"\d+\.\d+\.\d+", payload["version"])
    assert payload["version"] == "9.8.7"
    assert payload["environment"] == "test"
    assert payload["hostname"] == socket.gethostname()
    assert payload["pid"] == os.getpid() and isinstance(payload["pid"], int)
    assert payload["python_version"] == platform.python_version()
    assert payload["platform"] == platform.system()
    assert payload["architecture"] == platform.machine()
    assert datetime.fromisoformat(payload["started_at"]).tzinfo is not None
    assert datetime.fromisoformat(payload["started_at"]).utcoffset() == UTC.utcoffset(
        None
    )
    assert payload["timezone"] == "Etc/UTC"

    serialized = response.text.lower()
    for forbidden in (
        "database_url",
        "host",
        "port",
        "log_level",
        "password",
        "credential",
        "secret",
        "api_key",
    ):
        assert f'"{forbidden}"' not in serialized
