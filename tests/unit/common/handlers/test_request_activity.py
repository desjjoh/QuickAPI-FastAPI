import time
from unittest.mock import Mock

import pytest
from fastapi import Request
from starlette.types import Scope

from app.common.handlers.application_route import ApplicationRoute, transactional
from app.common.handlers.request_activity import RequestExpired, request_activity
from app.config import database

pytestmark = pytest.mark.unit


def test_monotonic_expiry_does_not_depend_on_timer_delivery() -> None:
    scope: Scope = {'type': 'http'}
    activity = request_activity(scope)

    assert request_activity(scope) is activity
    activity.assert_active()
    activity.expires_at = time.monotonic() - 1

    with pytest.raises(RequestExpired, match='Application response deadline'):
        activity.assert_active()

    activity.expires_at = float('inf')

    with pytest.raises(RequestExpired):
        activity.assert_active()


async def test_abandoned_request_cannot_allocate_mutation_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope: Scope = {'type': 'http'}
    activity = request_activity(scope)

    activity.abandon('Request disconnected.')
    activity.abandon('Later reason must not replace the first.')
    factory = Mock()

    monkeypatch.setattr(database, 'SessionLocal', factory)

    @transactional
    async def endpoint() -> dict[str, bool]:
        raise AssertionError('Expired work must not start')

    route = ApplicationRoute('/', endpoint=endpoint, methods=['POST'])

    with pytest.raises(RequestExpired, match='Request disconnected'):
        await route.get_route_handler()(Request(scope))

    factory.assert_not_called()


def test_invalid_shared_owner_is_rejected() -> None:
    with pytest.raises(RuntimeError, match='Invalid request activity'):
        request_activity({'type': 'http', 'quickapi.request_activity': object()})
