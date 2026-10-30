import asyncio
import signal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
import uvicorn

from app.common.handlers import http_server
from app.common.handlers.request_work import RequestWork

pytestmark = pytest.mark.unit


def server(monkeypatch: pytest.MonkeyPatch) -> http_server.ApplicationServer:
    monkeypatch.setattr(http_server.threading, 'Timer', Mock())
    config = uvicorn.Config('app.config.application:app', ws='none')
    config.loaded = True
    config.loaded_app = SimpleNamespace(
        state=SimpleNamespace(
            lifecycle=Mock(shutdown_failed=False), request_work=RequestWork(1)
        )
    )

    return http_server.ApplicationServer(config)


async def test_quiesce_is_immediate_and_shutdown_keeps_database_until_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = server(monkeypatch)
    state = cast(Any, value.config).loaded_app.state
    shutdown = AsyncMock()

    monkeypatch.setattr(uvicorn.Server, 'shutdown', shutdown)
    value.request_shutdown()
    state.lifecycle.quiesce.assert_called_once()
    assert state.request_work.draining_at is not None
    await value.shutdown()
    shutdown.assert_awaited_once()
    assert value.config.timeout_graceful_shutdown is not None
    assert 0 < value.config.timeout_graceful_shutdown <= 1
    state.request_work.failed = True

    with pytest.raises(RuntimeError, match='shutdown failed'):
        await value.shutdown()


async def test_server_drain_cancellation_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = server(monkeypatch)

    monkeypatch.setattr(
        uvicorn.Server,
        '_wait_tasks_to_complete',
        AsyncMock(side_effect=asyncio.CancelledError),
    )
    with pytest.raises(asyncio.CancelledError):
        await value._wait_tasks_to_complete()  # pyright: ignore[reportPrivateUsage] - isolated Uvicorn extension hook

    assert cast(Any, value.config).loaded_app.state.request_work.failed


def test_repeated_signal_forces_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    value = server(monkeypatch)

    def exit_failure(code: int) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(http_server.os, '_exit', exit_failure)
    value.handle_exit(signal.SIGTERM, None)
    assert value.should_exit
    with pytest.raises(SystemExit) as error:
        value.handle_exit(signal.SIGTERM, None)

    assert error.value.code == 1


def test_runner_failure_and_watchdog_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    value = server(monkeypatch)

    value.request_shutdown()
    monkeypatch.setattr(uvicorn.Server, 'run', Mock())
    with pytest.raises(RuntimeError, match='did not start'):
        value.run()

    cast(Mock, http_server.threading.Timer).return_value.cancel.assert_called_once()


@pytest.mark.parametrize('repeated', [False, True])
@pytest.mark.parametrize(
    'failure', [OSError('stderr closed'), BrokenPipeError('pipe closed')]
)
def test_forced_exit_survives_diagnostic_failure(
    monkeypatch: pytest.MonkeyPatch,
    repeated: bool,
    failure: OSError,
) -> None:
    value = server(monkeypatch)

    if repeated:
        value.request_shutdown()

    monkeypatch.setattr(http_server.os, 'write', Mock(side_effect=failure))

    def exit_failure(code: int) -> None:
        raise SystemExit(code)

    terminate = Mock(side_effect=exit_failure)

    monkeypatch.setattr(http_server.os, '_exit', terminate)
    with pytest.raises(SystemExit) as error:
        if repeated:
            value.handle_exit(signal.SIGTERM, None)
        else:
            value._force_exit()  # pyright: ignore[reportPrivateUsage] - final watchdog entrypoint

    assert error.value.code == 1
    terminate.assert_called_once_with(1)


async def test_interrupted_startup_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = server(monkeypatch)
    value.should_exit = True
    value.started = True

    monkeypatch.setattr(uvicorn.Server, 'startup', AsyncMock())
    shutdown = AsyncMock()

    monkeypatch.setattr(value, 'shutdown', shutdown)
    await value.startup()
    shutdown.assert_awaited_once_with(None)


async def test_listener_notice_follows_successful_server_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = server(monkeypatch)
    logger = Mock()

    monkeypatch.setattr(http_server, 'log', logger)

    async def started(*_: object) -> None:
        logger.info.assert_not_called()
        value.started = True

    monkeypatch.setattr(uvicorn.Server, 'startup', started)
    await value.startup()
    logger.info.assert_called_once_with(
        'HTTP server running on port 8000 — http://localhost:8000'
    )


async def test_signal_notice_is_early_named_and_emitted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = server(monkeypatch)
    logger = Mock()

    monkeypatch.setattr(http_server, 'log', logger)
    value.handle_exit(signal.SIGTERM, None)
    monkeypatch.setattr(uvicorn.Server, 'shutdown', AsyncMock())
    await value.shutdown()
    logger.warning.assert_called_once_with('SIGTERM received — initiating shutdown')
    assert cast(Any, value.config).loaded_app.state.shutdown_notice_logged is True


def test_clean_exit_record_follows_runner_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = server(monkeypatch)
    logger = Mock()

    monkeypatch.setattr(http_server, 'log', logger)

    def run(*_: object) -> None:
        logger.info.assert_not_called()
        value.started = True

    monkeypatch.setattr(uvicorn.Server, 'run', run)
    value.run()
    logger.info.assert_called_once_with('Application exited (code 0)')


def test_failed_startup_has_no_success_exit_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = server(monkeypatch)
    logger = Mock()

    monkeypatch.setattr(http_server, 'log', logger)
    monkeypatch.setattr(
        uvicorn.Server, 'run', Mock(side_effect=RuntimeError('startup failed'))
    )
    with pytest.raises(RuntimeError):
        value.run()

    logger.info.assert_not_called()
