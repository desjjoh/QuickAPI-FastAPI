import re

import httpx
import pytest
from prometheus_client import CONTENT_TYPE_LATEST

pytestmark = pytest.mark.e2e


def counter_value(text: str, *, route: str, status: int = 200) -> float:
    pattern = re.compile(
        rf'^http_requests_total\{{[^}}]*method="GET"[^}}]*route="{re.escape(route)}"'
        rf'[^}}]*status="{status}"[^}}]*\}} ([0-9.eE+-]+)$',
        re.MULTILINE,
    )
    match = pattern.search(text)

    return float(match.group(1)) if match else 0.0


async def test_metrics_exposes_prometheus_metadata(client: httpx.AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    assert "# HELP http_requests_total Total HTTP requests" in response.text
    assert "# TYPE http_requests_total counter" in response.text


async def test_metrics_excludes_scrapes_and_counts_known_traffic(
    client: httpx.AsyncClient,
) -> None:
    initial = await client.get("/metrics")

    assert 'route="/metrics"' not in initial.text
    assert counter_value(initial.text, route="/") == 0

    assert (await client.get("/")).status_code == 200
    assert (await client.get("/")).status_code == 200
    after_traffic = await client.get("/metrics")

    assert 'route="/metrics"' not in after_traffic.text
    assert counter_value(after_traffic.text, route="/") == 2
