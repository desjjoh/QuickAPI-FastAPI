from collections.abc import Iterator

import pytest

from app.config.metrics import REQUEST_COUNT, REQUEST_LATENCY


@pytest.fixture(autouse=True)
def isolated_prometheus_metrics() -> Iterator[None]:
    """Prevent request series created by one test leaking into another."""
    REQUEST_COUNT.clear()
    REQUEST_LATENCY.clear()
    yield
    REQUEST_COUNT.clear()
    REQUEST_LATENCY.clear()
