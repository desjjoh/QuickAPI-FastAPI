import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException, status

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_NAME", "QuickAPI")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")

from app.api.system.controllers import system_controller  # noqa: E402
from app.common.handlers.lifecycle_handler import LifecycleHandler  # noqa: E402

pytestmark = pytest.mark.unit


class ReadyProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lifecycle = LifecycleHandler()
        self.request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(lifecycle=self.lifecycle))
        )

    def test_ready_probe_raises_503_when_startup_is_incomplete(self) -> None:
        async def services_healthy() -> bool:
            return True

        with (
            patch.object(self.lifecycle, "is_ready", return_value=False),
            patch.object(
                self.lifecycle,
                "are_all_services_healthy",
                services_healthy,
            ),
        ):
            with self.assertRaises(HTTPException) as exc_info:
                asyncio.run(system_controller.ready_probe(self.request))  # type: ignore[arg-type]

        self.assertEqual(
            exc_info.exception.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(exc_info.exception.detail, "Application not ready.")

    def test_ready_probe_raises_503_when_services_are_unhealthy(self) -> None:
        async def services_unhealthy() -> bool:
            return False

        with (
            patch.object(self.lifecycle, "is_ready", return_value=True),
            patch.object(
                self.lifecycle,
                "are_all_services_healthy",
                services_unhealthy,
            ),
        ):
            with self.assertRaises(HTTPException) as exc_info:
                asyncio.run(system_controller.ready_probe(self.request))  # type: ignore[arg-type]

        self.assertEqual(
            exc_info.exception.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            exc_info.exception.detail,
            "One or more lifecycle services are unhealthy.",
        )

    def test_ready_probe_returns_ready_response_when_app_and_services_are_ready(
        self,
    ) -> None:
        async def services_healthy() -> bool:
            return True

        with (
            patch.object(self.lifecycle, "is_ready", return_value=True),
            patch.object(
                self.lifecycle,
                "are_all_services_healthy",
                services_healthy,
            ),
        ):
            response = asyncio.run(system_controller.ready_probe(self.request))  # type: ignore[arg-type]

        self.assertTrue(response.ready)
