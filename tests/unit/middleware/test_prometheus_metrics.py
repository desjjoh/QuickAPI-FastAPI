from unittest.mock import Mock

import pytest
from conftest import http_scope, invoke
from starlette.types import ASGIApp

from app.common.middleware.prometheus_metrics import PrometheusASGIMiddleware

pytestmark = pytest.mark.unit


async def test_collectors_are_labeled_without_global_state(
    app: ASGIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    count = Mock()
    latency = Mock()
    monkeypatch.setattr("app.common.middleware.prometheus_metrics.REQUEST_COUNT", count)
    monkeypatch.setattr(
        "app.common.middleware.prometheus_metrics.REQUEST_LATENCY", latency
    )
    await invoke(
        PrometheusASGIMiddleware(app), http_scope(method="POST", path="/items")
    )
    count.labels.assert_called_once_with("POST", "/items", "200")
    count.labels.return_value.inc.assert_called_once_with()
    latency.labels.assert_called_once_with("POST", "/items")


async def test_metrics_endpoint_is_not_instrumented(
    app: ASGIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    count = Mock()
    latency = Mock()
    monkeypatch.setattr("app.common.middleware.prometheus_metrics.REQUEST_COUNT", count)
    monkeypatch.setattr(
        "app.common.middleware.prometheus_metrics.REQUEST_LATENCY", latency
    )

    await invoke(PrometheusASGIMiddleware(app), http_scope(path="/metrics"))

    count.labels.assert_not_called()
    latency.labels.assert_not_called()
