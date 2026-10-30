import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Response, status
from pydantic import ValidationError

from app.api.system.controllers import system_controller
from app.api.system.controllers.system_controller import ready_probe
from app.api.system.services.system_service import SystemService
from app.common.handlers.lifecycle_handler import LifecycleHandler

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    'operation,method,result,field',
    [
        ('root', 'root', {}, ('message',)),
        (
            'live_probe',
            'live',
            {'alive': True, 'uptime': -1, 'timestamp': datetime.now(UTC)},
            ('uptime',),
        ),
        ('info', 'info', {'version': 'invalid'}, ('version',)),
        ('system', 'collect', {'cpu': {'cores': 0}}, ('cpu', 'cores')),
    ],
)
async def test_system_controller_validates_collected_data(
    operation: str,
    method: str,
    result: object,
    field: tuple[str, ...],
) -> None:
    service = Mock()

    setattr(
        service,
        method,
        (
            AsyncMock(return_value=result)
            if method == 'collect'
            else Mock(return_value=result)
        ),
    )
    controller = cast(
        Callable[..., Awaitable[object]], getattr(system_controller, operation)
    )

    with pytest.raises(ValidationError) as error:
        await controller(service=service)

    assert any(detail['loc'] == field for detail in error.value.errors())


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


def service_for(lifecycle: LifecycleHandler) -> SystemService:
    return SystemService(lifecycle, datetime.now(UTC), time.perf_counter())


async def test_ready_probe_returns_the_contract_when_ready() -> None:
    lifecycle = LifecycleHandler()

    lifecycle.register([Service()])
    await lifecycle.startup()

    response = Response()
    payload = await ready_probe(response, service_for(lifecycle))
    body = payload.model_dump(mode='json')

    assert response.status_code == status.HTTP_200_OK
    assert body["ready"] is True
    assert body["status"] == "ready"
    assert set(body) == {"ready", "status", "timestamp"}
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

    response = Response()
    payload = await ready_probe(response, service_for(lifecycle))
    body = payload.model_dump(mode='json')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert body["ready"] is False
    assert body["status"] == "not_ready"
    assert set(body) == {"ready", "status", "timestamp"}
