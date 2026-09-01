import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi import status

from app.api.system.controllers.system_controller import ready_probe
from app.common.handlers.lifecycle_handler import LifecycleHandler

pytestmark = pytest.mark.unit


@dataclass
class Service:
    name: str = "dependency"
    healthy: bool = True

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def check(self) -> bool:
        return self.healthy


def request_for(lifecycle: LifecycleHandler) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(lifecycle=lifecycle))
    )


async def test_ready_probe_returns_the_contract_when_ready() -> None:
    lifecycle = LifecycleHandler()
    lifecycle.register([Service()])
    await lifecycle.startup()

    response = await ready_probe(request_for(lifecycle))  # type: ignore[arg-type]
    body = json.loads(bytes(response.body))

    assert response.status_code == status.HTTP_200_OK
    assert body["ready"] is True
    assert body["status"] == "ready"
    assert body["checks"][0]["name"] == "dependency"
    assert body["checks"][0]["status"] == "up"
    assert body["timestamp"].endswith("Z")


@pytest.mark.parametrize("shutdown", [False, True])
async def test_ready_probe_returns_same_contract_during_incomplete_startup_or_shutdown(
    shutdown: bool,
) -> None:
    lifecycle = LifecycleHandler()
    lifecycle.register([Service()])
    if shutdown:
        await lifecycle.startup()
        await lifecycle.shutdown()

    response = await ready_probe(request_for(lifecycle))  # type: ignore[arg-type]
    body = json.loads(bytes(response.body))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert body["ready"] is False
    assert body["status"] == "not_ready"
    assert body["checks"][0]["status"] == "up"
