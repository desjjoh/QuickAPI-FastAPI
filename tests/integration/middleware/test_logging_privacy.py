import io
import json
import os
import subprocess
import sys
from typing import Literal

import httpx
import pytest

from app.config.application import create_app
from app.config.logging import create_logger

from .test_timeout_server import running

pytestmark = pytest.mark.integration
SECRET = "private-value-never-log"


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_real_server_failure_uses_safe_correlated_json(
    protocol: Literal["h11", "httptools"], monkeypatch: pytest.MonkeyPatch
) -> None:
    output = io.StringIO()
    logger = create_logger(production=True, level="DEBUG", stream=output)
    for module in [
        "app.config.logging",
        "app.common.handlers.exception_handler",
        "app.common.middleware.request_logger",
        "app.common.middleware.request_timeout",
    ]:
        monkeypatch.setattr(module + ".log", logger)
    app = create_app()

    @app.get("/private/{identifier}")
    async def fail(identifier: str) -> None:
        raise RuntimeError(SECRET)

    async with running(app, protocol) as port:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://127.0.0.1:{port}/private/{SECRET}?token={SECRET}"
            )
            assert response.status_code == 500
            assert response.json()["message"] == "Internal server error."
    assert SECRET not in output.getvalue()
    entries = [json.loads(line) for line in output.getvalue().splitlines()]
    failure = next(entry for entry in entries if entry["msg"] == "HTTP request failed.")
    access = [entry for entry in entries if entry.get("outcome") == "completed"]
    assert len(access) == 1
    assert failure["requestId"] == access[0]["requestId"]
    assert access[0]["route"] == "/private/{identifier}" and access[0]["status"] == 500
    assert failure["error"]["errorType"] == "RuntimeError"
    assert all("Traceback" not in entry["msg"] for entry in entries)


@pytest.mark.parametrize("environment", ["development", "production"])
def test_invalid_environment_never_prints_supplied_values(environment: str) -> None:
    env = {**os.environ, "ENV": environment, "APP_VERSION": SECRET}
    result = subprocess.run(
        [sys.executable, "-c", "import app.config.environment"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert SECRET not in result.stdout + result.stderr
    assert "APP_VERSION" in result.stdout
    if environment == "production":
        data = json.loads(result.stdout)
        assert data["levelLabel"] == "critical" and data["fields"] == ["APP_VERSION"]
        assert "\x1b" not in result.stdout
    else:
        assert "Environment validation failed" in result.stdout


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARN", "ERROR"])
def test_dependency_threshold_and_message_privacy_in_fresh_process(level: str) -> None:
    code = """
import logging
from app.config.logging import log
logging.getLogger('asyncmy').debug('private-value-never-log')
# Reproduce unlisted reload/dependency loggers, including an explicit child level.
for name in ('watchfiles.main', 'unlisted_dependency.child'):
    dependency = logging.getLogger(name)
    dependency.setLevel(logging.DEBUG)
    dependency.debug('private-value-never-log')
    dependency.info('private-value-never-log')
logging.getLogger('watchfiles.main').warning('private-value-never-log')
logging.getLogger('sqlalchemy.engine').error('private-value-never-log %s', 'private-value-never-log')
log.debug('Successful request.')
log.info('Application ready.')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "ENV": "production", "LOG_LEVEL": level},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0 and not result.stderr
    assert SECRET not in result.stdout
    entries = [json.loads(line) for line in result.stdout.splitlines()]
    dependencies = [
        entry for entry in entries if entry["msg"] == "Dependency log event."
    ]
    assert [entry["levelLabel"] for entry in dependencies] == (
        ["error"] if level == "ERROR" else ["warning", "error"]
    )
    assert any(entry["msg"] == "Successful request." for entry in entries) == (
        level == "DEBUG"
    )
    assert any(entry["msg"] == "Application ready." for entry in entries) == (
        level in {"DEBUG", "INFO"}
    )


@pytest.mark.parametrize("environment", ["development", "production"])
def test_fatal_server_initialization_is_safe(environment: str) -> None:
    code = """
from app import main

def fail(*args, **kwargs):
    raise RuntimeError('private-value-never-log')
main.ApplicationServer=fail
main.run()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "ENV": environment},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1 and SECRET not in result.stdout + result.stderr
    assert not result.stderr
    if environment == "production":
        entry = json.loads(result.stdout)
        assert (
            entry["levelLabel"] == "critical"
            and entry["error"]["errorType"] == "RuntimeError"
        )
    else:
        assert "Fatal error during server initialization" in result.stdout
