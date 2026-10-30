from pathlib import Path
from unittest.mock import Mock

import pytest

from app import main as entrypoint

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("environment", "reload_enabled"),
    [("development", True), ("production", False), ("test", False)],
)
def test_main_forwards_settings_and_selects_reload_by_environment(
    monkeypatch: pytest.MonkeyPatch, environment: str, reload_enabled: bool
) -> None:
    config = Mock(should_reload=reload_enabled)
    configure = Mock(return_value=config)
    server = Mock()
    supervisor = Mock()

    monkeypatch.setattr(entrypoint.uvicorn, "Config", configure)
    monkeypatch.setattr(entrypoint, "ApplicationServer", Mock(return_value=server))
    monkeypatch.setattr(entrypoint, "ChangeReload", supervisor)
    monkeypatch.setattr(entrypoint.settings, "HOST", "127.0.0.9")
    monkeypatch.setattr(entrypoint.settings, "PORT", 9123)
    monkeypatch.setattr(entrypoint.settings, "ENV", environment)

    entrypoint.main()

    configure.assert_called_once_with(
        "app.config.application:app",
        host="127.0.0.9",
        port=9123,
        reload=reload_enabled,
        reload_dirs=(
            [str(Path(entrypoint.__file__).resolve().parent)]
            if reload_enabled
            else None
        ),
        ws="none",
        loop="app.config.event_loop:server_loop_factory",
        log_config=None,
        proxy_headers=False,
    )
    if reload_enabled:
        supervisor.assert_called_once_with(
            config, target=server.run, sockets=[config.bind_socket.return_value]
        )
        supervisor.return_value.run.assert_called_once()
    else:
        server.run.assert_called_once()


def test_run_reports_fatal_startup_error_without_starting_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    uvicorn_run = Mock(side_effect=RuntimeError("cannot bind"))

    monkeypatch.setattr(entrypoint, "ApplicationServer", uvicorn_run)

    with pytest.raises(SystemExit) as error:
        entrypoint.run()

    assert error.value.code == 1
    assert "Fatal error during server initialization" in capsys.readouterr().out
    uvicorn_run.assert_called_once()
