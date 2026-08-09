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
    uvicorn_run = Mock()
    monkeypatch.setattr(entrypoint.uvicorn, "run", uvicorn_run)
    monkeypatch.setattr(entrypoint.settings, "HOST", "127.0.0.9")
    monkeypatch.setattr(entrypoint.settings, "PORT", 9123)
    monkeypatch.setattr(entrypoint.settings, "ENV", environment)

    entrypoint.main()

    uvicorn_run.assert_called_once_with(
        "app.config.application:app",
        host="127.0.0.9",
        port=9123,
        reload=reload_enabled,
        log_config=None,
    )


def test_run_reports_fatal_startup_error_without_starting_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    uvicorn_run = Mock(side_effect=RuntimeError("cannot bind"))
    monkeypatch.setattr(entrypoint.uvicorn, "run", uvicorn_run)

    with pytest.raises(SystemExit) as error:
        entrypoint.run()

    assert error.value.code == 1
    assert "Fatal error during server initialization" in capsys.readouterr().out
    uvicorn_run.assert_called_once()
