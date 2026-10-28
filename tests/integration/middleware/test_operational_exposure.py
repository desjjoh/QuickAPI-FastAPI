from itertools import product
from typing import Any, Literal, cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI

from app.common.handlers.lifecycle_handler import ReadinessCheckResult
from app.config.application import create_app
from app.config.environment import Settings, settings
from app.config.metrics import REQUEST_COUNT

from .test_timeout_server import running

pytestmark = pytest.mark.integration
FLAGS = ("DOCS_ENABLED", "DIAGNOSTICS_ENABLED", "METRICS_ENABLED")


def application(
    monkeypatch: pytest.MonkeyPatch, environment: str = "production", **overrides: str
) -> FastAPI:
    for key in FLAGS:
        monkeypatch.delenv(key, raising=False)
    factory = cast(Any, Settings)
    policy = cast(
        Settings,
        factory(
            _env_file=None,
            **{
                **settings.model_dump(exclude=set(FLAGS)),
                "ENV": environment,
                **overrides,
            },
        ),
    )
    for key in (*FLAGS, "ENV"):
        monkeypatch.setattr(settings, key, getattr(policy, key))
    monkeypatch.setattr(
        "app.config.rate_limiter.RateLimiter.allow", Mock(return_value=True)
    )
    return create_app()


async def status(client: httpx.AsyncClient, path: str) -> int:
    return (await client.get(path)).status_code


@pytest.mark.parametrize("environment", ["development", "test", "production"])
async def test_environment_defaults_through_actual_stack(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = application(monkeypatch, environment)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for path in [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/info",
            "/system",
            "/metrics",
        ]:
            assert await status(client, path) == (
                404 if environment == "production" else 200
            )


@pytest.mark.parametrize(
    "docs,diagnostics,metrics", list(product([False, True], repeat=3))
)
async def test_independent_flags_and_registered_schema(
    docs: bool, diagnostics: bool, metrics: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = application(
        monkeypatch,
        DOCS_ENABLED=str(docs).lower(),
        DIAGNOSTICS_ENABLED=str(diagnostics).lower(),
        METRICS_ENABLED=str(metrics).lower(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for path, enabled in [
            ("/docs", docs),
            ("/redoc", docs),
            ("/openapi.json", docs),
            ("/docs/oauth2-redirect", docs),
            ("/info", diagnostics),
            ("/system", diagnostics),
            ("/metrics", metrics),
        ]:
            assert await status(client, path) == (200 if enabled else 404)
        if docs:
            schema = (await client.get("/openapi.json")).json()
            assert ("/info" in schema["paths"]) == diagnostics
            assert ("/system" in schema["paths"]) == diagnostics
            assert ("/metrics" in schema["paths"]) == metrics
            assert set(
                schema["components"]["schemas"]["ReadyResponse"]["properties"]
            ) == {"ready", "status", "timestamp"}


async def test_disabled_families_never_execute_handlers_or_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = application(
        monkeypatch,
        "development",
        DOCS_ENABLED="false",
        DIAGNOSTICS_ENABLED="false",
        METRICS_ENABLED="false",
    )
    diagnostics = AsyncMock(side_effect=AssertionError("diagnostics ran"))
    info = Mock(side_effect=AssertionError("info ran"))
    metrics = Mock(side_effect=AssertionError("metrics exposition ran"))
    schema = Mock(side_effect=AssertionError("schema generated"))
    monkeypatch.setattr(
        "app.api.system.services.system_service.SystemDiagnosticsService.collect",
        diagnostics,
    )
    monkeypatch.setattr(
        "app.api.system.services.system_service.SystemInfoService.info", info
    )
    monkeypatch.setattr(
        "app.api.system.controllers.system_controller.generate_latest", metrics
    )
    monkeypatch.setattr(app, "openapi", schema)

    @app.get("/info/nested")
    async def accidental_route() -> None:
        pytest.fail("Disabled family must be reserved, even if a nested route is added")

    @app.get("/information")
    async def separate_route() -> dict[str, bool]:
        return {"ok": True}

    paths = [
        "/docs",
        "/docs/",
        "/docs/oauth2-redirect",
        "/docs/swagger-ui.css",
        "/docs/swagger-ui-init.js",
        "/openapi.json",
        "/openapi.json/",
        "/redoc",
        "/redoc/",
        "/info",
        "/info/",
        "/info/nested",
        "/INFO",
        "/system",
        "/system/",
        "/metrics",
        "/metrics/",
        "/metrics/nested",
        "/%6detrics",
        "/MeTrIcS",
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        for path in paths:
            for method in ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]:
                if method in {"POST", "PUT", "PATCH"}:
                    result = await client.request(
                        method,
                        path,
                        content=b"{}",
                        headers={"content-type": "application/json"},
                    )
                else:
                    result = await client.request(method, path)
                assert result.status_code == 404, (method, path)
                assert "location" not in result.headers
                assert result.headers["x-content-type-options"] == "nosniff"
                assert "content-security-policy" in result.headers
                if method != "HEAD":
                    assert result.json()["status"] == 404
                    assert result.json()["message"] == "Not Found"
        assert await status(client, "/information") == 200
    diagnostics.assert_not_called()
    info.assert_not_called()
    metrics.assert_not_called()
    schema.assert_not_called()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, root_path="/service"), base_url="http://test"
    ) as mounted:
        assert await status(mounted, "/service/metrics") == 404
        assert await status(mounted, "/service/info/nested") == 404


@pytest.mark.parametrize("healthy", [False, True])
@pytest.mark.parametrize("diagnostics_enabled", [False, True])
async def test_public_probes_stay_minimal_and_check_dependencies(
    healthy: bool, diagnostics_enabled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = application(monkeypatch, DIAGNOSTICS_ENABLED=str(diagnostics_enabled).lower())
    check = AsyncMock(
        return_value=[
            ReadinessCheckResult(
                name="private-db-secret",
                status="up" if healthy else "down",
                response_time_ms=123.456,
            )
        ]
    )
    monkeypatch.setattr(app.state.lifecycle, "check_services", check)
    monkeypatch.setattr(app.state.lifecycle, "is_ready", Mock(return_value=True))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert await status(client, "/") == 200
        assert await status(client, "/health") == 200
        check.assert_not_called()
        ready = await client.get("/ready")
    check.assert_awaited_once()
    assert ready.status_code == (200 if healthy else 503)
    assert ready.json()["ready"] is healthy
    assert set(ready.json()) == {"ready", "status", "timestamp"}
    assert "private-db-secret" not in ready.text and "123.456" not in ready.text


async def test_metrics_collection_continues_while_exposition_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = application(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert await status(client, "/") == 200
        assert await status(client, "/metrics") == 404
    recorded = [
        sample
        for family in REQUEST_COUNT.collect()
        for sample in family.samples
        if sample.name == "http_requests_total"
    ]
    assert len(recorded) == 1
    assert recorded[0].labels == {"method": "GET", "route": "/", "status": "200"}
    assert recorded[0].value == 1


async def test_differently_configured_apps_do_not_leak_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hidden = application(monkeypatch)
    visible = application(
        monkeypatch,
        DOCS_ENABLED="true",
        DIAGNOSTICS_ENABLED="true",
        METRICS_ENABLED="true",
    )
    for app, expected in [(visible, 200), (hidden, 404), (visible, 200)]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            for path in ["/info", "/metrics", "/docs"]:
                assert await status(client, path) == expected


@pytest.mark.parametrize("protocol", ["h11", "httptools"])
async def test_production_defaults_over_real_server(
    protocol: Literal["h11", "httptools"], monkeypatch: pytest.MonkeyPatch
) -> None:
    app = application(monkeypatch)
    async with running(app, protocol) as port:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", follow_redirects=False
        ) as client:
            for path in [
                "/docs",
                "/docs/",
                "/openapi.json",
                "/redoc",
                "/info",
                "/system",
                "/metrics/",
            ]:
                assert await status(client, path) == 404
            assert (await client.head("/info")).status_code == 404
            assert await status(client, "/health") == 200
            ready = await client.get("/ready")
            assert ready.status_code == 503  # This fixture intentionally skips startup.
            assert set(ready.json()) == {"ready", "status", "timestamp"}


@pytest.mark.parametrize("trusted", [False, True])
async def test_forwarded_identity_cannot_enable_hidden_endpoints(
    trusted: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TRUST_PROXY", ["127.0.0.1"] if trusted else [])
    exporter = Mock(side_effect=AssertionError("hidden exporter ran"))
    monkeypatch.setattr(
        "app.api.system.controllers.system_controller.generate_latest", exporter
    )
    app = application(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, client=("127.0.0.1", 123)),
        base_url="http://test",
    ) as client:
        for path in ["/info", "/system", "/metrics", "/docs"]:
            response = await client.get(
                path,
                headers={
                    "x-forwarded-for": "198.51.100.8",
                    "x-forwarded-proto": "https",
                },
            )
            assert response.status_code == (404 if trusted else 400)
    exporter.assert_not_called()
