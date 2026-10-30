"""Windows asyncmy TLS needs a selector loop for its mid-connection socket upgrade."""

import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from uvicorn.loops.auto import auto_loop_factory


def database_loop_factory() -> Callable[[], asyncio.AbstractEventLoop]:
    from app.config.environment import settings

    if sys.platform == "win32" and settings.DB_SSL:
        return asyncio.SelectorEventLoop

    return asyncio.new_event_loop


def server_loop_factory() -> asyncio.AbstractEventLoop:
    from app.config.environment import settings

    if sys.platform == "win32" and settings.DB_SSL:
        return asyncio.SelectorEventLoop()

    return auto_loop_factory(use_subprocess=settings.ENV == "development")()


def run_database[T](coroutine: Coroutine[Any, Any, T]) -> T:
    with asyncio.Runner(loop_factory=database_loop_factory()) as runner:
        return runner.run(coroutine)
