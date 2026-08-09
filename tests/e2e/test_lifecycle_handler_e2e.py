import asyncio
import unittest

import pytest

from app.common.handlers.lifecycle_handler import LifecycleHandler
from app.config.application import create_app, lifespan

pytestmark = pytest.mark.e2e


class StubService:
    def __init__(self, name: str, fail_start: bool = False) -> None:
        self.name = name
        self.fail_start = fail_start
        self.starts = 0
        self.stops = 0

    async def start(self) -> None:
        self.starts += 1
        if self.fail_start:
            raise RuntimeError("startup failed")

    async def stop(self) -> None:
        self.stops += 1

    async def check(self) -> bool:
        return True


class LifecycleHandlerTests(unittest.TestCase):
    def test_two_consecutive_lifespan_cycles_restart_each_service_once(self) -> None:
        async def run_cycles() -> None:
            service = StubService("database")
            app = create_app()
            app.state.lifecycle = LifecycleHandler()
            app.state.lifecycle.register([service, service])

            for cycle in range(1, 3):
                async with lifespan(app):
                    self.assertTrue(app.state.lifecycle.is_ready())
                    self.assertEqual(service.starts, cycle)

                self.assertFalse(app.state.lifecycle.is_ready())
                self.assertEqual(service.stops, cycle)

        asyncio.run(run_cycles())

    def test_each_application_has_its_own_lifecycle(self) -> None:
        first = create_app()
        second = create_app()

        self.assertIsNot(first.state.lifecycle, second.state.lifecycle)

    def test_startup_failure_rolls_back_services_that_started(self) -> None:
        async def run_startup() -> None:
            started = StubService("started")
            failing = StubService("failing", fail_start=True)
            lifecycle = LifecycleHandler()
            lifecycle.register([started, failing])

            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                await lifecycle.startup()

            self.assertEqual(started.stops, 1)
            self.assertEqual(failing.stops, 0)
            self.assertFalse(lifecycle.is_ready())

            await lifecycle.shutdown()
            self.assertEqual(started.stops, 1)

        asyncio.run(run_startup())
