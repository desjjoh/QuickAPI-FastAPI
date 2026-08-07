from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.config.environment import Settings

pytestmark = pytest.mark.unit


ENV_KEYS = (
    "APP_NAME",
    "APP_VERSION",
    "ENV",
    "LOG_LEVEL",
    "HOST",
    "PORT",
    "DATABASE_URL",
)


def settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    values = {
        "APP_NAME": "QuickAPI",
        "APP_VERSION": "1.2.3",
        "ENV": "test",
        "PORT": "8000",
        "DATABASE_URL": "sqlite:///test.db",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings_factory = cast(Any, Settings)
    return cast(Settings, settings_factory(_env_file=None))


def test_valid_settings_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    result = settings(monkeypatch)
    assert result.APP_NAME == "QuickAPI"
    assert result.LOG_LEVEL == "INFO"
    assert result.HOST == "0.0.0.0"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("APP_VERSION", "1.2"),
        ("ENV", "staging"),
        ("LOG_LEVEL", "debug"),
        ("PORT", "0"),
        ("PORT", "65536"),
        ("PORT", "not-a-number"),
        ("DATABASE_URL", "x"),
        ("APP_NAME", ""),
    ],
)
def test_malformed_values(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        settings(monkeypatch, **{key: value})


@pytest.mark.parametrize("environment", ["development", "production", "test"])
def test_supported_environments_are_isolated(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    assert settings(monkeypatch, ENV=environment).ENV == environment


def test_environment_names_are_case_sensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("app_name", "wrong")
    assert settings(monkeypatch).APP_NAME == "QuickAPI"
