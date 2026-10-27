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
    "API_PUBLISHED_PORT",
    "MYSQL_PUBLISHED_PORT",
    "DATABASE_URL",
    "TIMEZONE",
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
    assert result.TIMEZONE == "Etc/UTC"
    assert result.API_PUBLISHED_PORT == 8000
    assert result.MYSQL_PUBLISHED_PORT == 3308


def test_published_port_overrides_do_not_change_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = settings(
        monkeypatch, PORT="5000", API_PUBLISHED_PORT="8001", MYSQL_PUBLISHED_PORT="3309"
    )
    assert result.PORT == 5000
    assert result.API_PUBLISHED_PORT == 8001
    assert result.MYSQL_PUBLISHED_PORT == 3309


def test_empty_published_ports_use_compose_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = settings(monkeypatch, API_PUBLISHED_PORT="", MYSQL_PUBLISHED_PORT="")
    assert result.API_PUBLISHED_PORT == 8000
    assert result.MYSQL_PUBLISHED_PORT == 3308


@pytest.mark.parametrize("key", ["API_PUBLISHED_PORT", "MYSQL_PUBLISHED_PORT"])
@pytest.mark.parametrize("value", ["1", "65535"])
def test_published_port_boundaries(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    assert getattr(settings(monkeypatch, **{key: value}), key) == int(value)


@pytest.mark.parametrize("key", ["API_PUBLISHED_PORT", "MYSQL_PUBLISHED_PORT"])
@pytest.mark.parametrize("value", ["0", "-1", "65536", "8000.0", "invalid", " "])
def test_invalid_published_ports_fail_validation(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError) as error:
        settings(monkeypatch, **{key: value})
    assert error.value.errors()[0]["loc"] == (key,)


def test_configured_iana_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings(monkeypatch, TIMEZONE="America/New_York").TIMEZONE == (
        "America/New_York"
    )


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
        ("TIMEZONE", "Not/A_Timezone"),
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
