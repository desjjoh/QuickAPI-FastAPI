import io
import re
from pathlib import Path
from typing import Any, cast

import pytest
from dotenv import dotenv_values
from pydantic import ValidationError

from app.config.environment import Settings

pytestmark = pytest.mark.unit


def settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for key in Settings.model_fields:
        monkeypatch.delenv(key, raising=False)

    values = {
        "APP_NAME": "QuickAPI",
        "APP_VERSION": "1.2.3",
        "ENV": "test",
        "PORT": "8000",
        "DATABASE_URL": "mysql+asyncmy://test:test@localhost/test",
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
    assert result.MYSQL_PUBLISHED_PORT == 3310


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
    assert result.MYSQL_PUBLISHED_PORT == 3310


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


HTTP_NUMBERS = {
    "REQUEST_TIMEOUT_MS": (10000, 1, 2147483647),
    "REQUEST_FIRST_BODY_TIMEOUT_MS": (5000, 1, 2147483647),
    "REQUEST_CHUNK_TIMEOUT_MS": (2000, 1, 2147483647),
    "HTTP_MAX_BODY_BYTES": (1048576, 1, 1073741824),
    "HTTP_MAX_HEADER_COUNT": (100, 1, 10000),
    "HTTP_MAX_SINGLE_HEADER_BYTES": (4096, 1, 1048576),
    "HTTP_MAX_TOTAL_HEADER_BYTES": (8192, 1, 16777216),
    "CORS_MAX_AGE_SECONDS": (86400, 0, 86400),
}


def test_http_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    result = settings(monkeypatch)

    for key, (default, _, _) in HTTP_NUMBERS.items():
        assert getattr(result, key) == default

    assert result.CORS_ORIGINS == ["http://localhost:3000"]
    assert result.CORS_CREDENTIALS is True
    assert result.TRUST_PROXY == []
    assert set(result.CORS_METHODS) <= set(result.HTTP_ALLOWED_METHODS)
    assert result.HTTP_ALLOWED_CONTENT_TYPES == [
        "application/json",
        "multipart/form-data",
    ]


@pytest.mark.parametrize("key", HTTP_NUMBERS)
@pytest.mark.parametrize("value", ["", " ", "-1", "1.5", "nan", "inf", "1e3", "true"])
def test_http_numbers_reject_invalid_syntax(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        settings(monkeypatch, **{key: value})


@pytest.mark.parametrize("key", HTTP_NUMBERS)
def test_http_numeric_ranges(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    _, lower, upper = HTTP_NUMBERS[key]

    for value in [lower - 1, upper + 1]:
        with pytest.raises(ValidationError):
            settings(monkeypatch, **{key: str(value)})

    # Exercise boundaries with compatible related budgets, not accidental relation failures.
    compatible = {
        "REQUEST_TIMEOUT_MS": "2147483647",
        "REQUEST_FIRST_BODY_TIMEOUT_MS": "1",
        "REQUEST_CHUNK_TIMEOUT_MS": "1",
        "HTTP_MAX_SINGLE_HEADER_BYTES": "1",
        "HTTP_MAX_TOTAL_HEADER_BYTES": "16777216",
    }

    for value in [lower, upper]:
        assert (
            getattr(settings(monkeypatch, **{**compatible, key: str(value)}), key)
            == value
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("CORS_ORIGINS", "*"),
        ("CORS_ORIGINS", "https://site.test/"),
        ("CORS_ORIGINS", "https://user:password@site.test"),
        ("CORS_ORIGINS", "https://site.test?q=1"),
        ("CORS_ORIGINS", "https://site.test#x"),
        ("CORS_ORIGINS", "https://site.test:0"),
        ("CORS_ORIGINS", "https://site.test:99999"),
        ("CORS_ORIGINS", "https://site.test:443"),
        ("CORS_ORIGINS", "https://site.test:0008443"),
        ("CORS_ORIGINS", "https://[2001:0DB8::1]"),
        ("CORS_ORIGINS", "https://site.test:"),
        ("CORS_ORIGINS", "https://site.test\\evil"),
        ("CORS_ORIGINS", "null"),
        ("CORS_ORIGINS", ""),
        ("CORS_ORIGINS", "https://ok.test,,https://another.test"),
        ("CORS_METHODS", "get"),
        ("CORS_METHODS", "TRACE"),
        ("HTTP_ALLOWED_METHODS", "CONNECT"),
        ("HTTP_ALLOWED_METHODS", ""),
        ("HTTP_ALLOWED_CONTENT_TYPES", "application/*"),
        ("HTTP_ALLOWED_CONTENT_TYPES", ""),
        ("HTTP_ALLOWED_CONTENT_TYPES", "application/json;charset=utf-8"),
        ("CORS_ALLOWED_HEADERS", "x-header\r\nInjected: yes"),
        ("CORS_ALLOWED_HEADERS", "x-forwarded-for"),
        ("CORS_EXPOSED_HEADERS", "connection"),
        ("CORS_CREDENTIALS", "1"),
        ("CORS_CREDENTIALS", "TRUE"),
        ("CORS_CREDENTIALS", ""),
        ("TRUST_PROXY", "*"),
        ("TRUST_PROXY", "true"),
        ("TRUST_PROXY", "1"),
        ("TRUST_PROXY", "0.0.0.0/0"),
        ("TRUST_PROXY", "::/0"),
        ("TRUST_PROXY", "localhost"),
        ("TRUST_PROXY", "127.0.0.1/33"),
        ("TRUST_PROXY", "fe80::1%eth0"),
        ("TRUST_PROXY", "10.0.0.0/255.0.0.0"),
        ("TRUST_PROXY", "10.0.0.0/\u0668"),
        ("TRUST_PROXY", "127.0.0.1,,10.0.0.0/8"),
    ],
)
def test_http_policy_rejects_malformed_values(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        settings(monkeypatch, **{key: value})


def test_http_policy_overrides_and_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = settings(
        monkeypatch,
        CORS_ORIGINS=" https://example.test, http://localhost:5173,https://example.test ",
        CORS_ALLOWED_HEADERS="Content-Type, X-Custom, x-custom",
        CORS_EXPOSED_HEADERS="",
        CORS_CREDENTIALS="false",
        CORS_MAX_AGE_SECONDS="0",
        TRUST_PROXY="127.0.0.1, 10.1.2.3/8, ::1",
        HTTP_ALLOWED_CONTENT_TYPES="Application/JSON,text/plain",
    )

    assert result.CORS_ORIGINS == ["https://example.test", "http://localhost:5173"]
    assert result.CORS_ALLOWED_HEADERS == ["content-type", "x-custom"]
    assert result.CORS_EXPOSED_HEADERS == []
    assert result.CORS_CREDENTIALS is False and result.CORS_MAX_AGE_SECONDS == 0
    assert result.TRUST_PROXY == ["127.0.0.1/32", "10.0.0.0/8", "::1/128"]
    assert result.HTTP_ALLOWED_CONTENT_TYPES == ["application/json", "text/plain"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"REQUEST_FIRST_BODY_TIMEOUT_MS": "10001"},
        {"REQUEST_CHUNK_TIMEOUT_MS": "10001"},
        {"HTTP_MAX_SINGLE_HEADER_BYTES": "8193"},
        {"HTTP_ALLOWED_METHODS": "GET"},
    ],
)
def test_incompatible_http_settings_fail(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str]
) -> None:
    with pytest.raises(ValidationError):
        settings(monkeypatch, **overrides)


@pytest.mark.parametrize(
    "key",
    [
        "CORS_ORIGINS",
        "CORS_ALLOWED_HEADERS",
        "TRUST_PROXY",
        "HTTP_ALLOWED_CONTENT_TYPES",
    ],
)
def test_policy_list_bounds(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    values = {
        "CORS_ORIGINS": [f"https://host-{index}.test" for index in range(101)],
        "CORS_ALLOWED_HEADERS": [f"x-header-{index}" for index in range(101)],
        "TRUST_PROXY": [f"10.0.0.{index}" for index in range(101)],
        "HTTP_ALLOWED_CONTENT_TYPES": [
            f"application/type-{index}" for index in range(101)
        ],
    }

    with pytest.raises(ValidationError):
        settings(monkeypatch, **{key: ",".join(values[key])})


def test_environment_overrides_dotenv_and_missing_values_use_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings(monkeypatch)
    dotenv = tmp_path / "policy.env"

    dotenv.write_text(
        'CORS_ORIGINS="https://file.example"\nREQUEST_TIMEOUT_MS=6000\n',
        encoding="utf-8",
    )
    factory = cast(Any, Settings)
    file_settings = cast(Settings, factory(_env_file=dotenv))

    assert file_settings.CORS_ORIGINS == ["https://file.example"]
    assert file_settings.REQUEST_TIMEOUT_MS == 6000
    assert file_settings.HTTP_MAX_BODY_BYTES == 1048576
    monkeypatch.setenv("CORS_ORIGINS", "https://process.example")
    monkeypatch.setenv("REQUEST_TIMEOUT_MS", "7000")
    process_settings = cast(Settings, factory(_env_file=dotenv))

    assert process_settings.CORS_ORIGINS == ["https://process.example"]
    assert process_settings.REQUEST_TIMEOUT_MS == 7000
    assert (
        cast(
            Settings, factory(_env_file=dotenv, REQUEST_TIMEOUT_MS=8000)
        ).REQUEST_TIMEOUT_MS
        == 8000
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("CORS_ORIGINS", 123),
        ("CORS_ORIGINS", ["https://ok.test", 123]),
        ("HTTP_MAX_BODY_BYTES", True),
        ("REQUEST_TIMEOUT_MS", 1.5),
        ("CORS_CREDENTIALS", 1),
    ],
)
def test_python_configuration_rejects_ambiguous_types(
    monkeypatch: pytest.MonkeyPatch, key: str, value: object
) -> None:
    values = settings(monkeypatch).model_dump()

    with pytest.raises(ValidationError):
        Settings.model_validate({**values, key: value})


def test_example_optional_http_values_match_code_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = settings(monkeypatch)
    text = (Path(__file__).resolve().parents[3] / ".env.example").read_text(
        encoding="utf-8"
    )
    lines = [
        line[2:] for line in text.splitlines() if re.match(r"# [A-Z][A-Z0-9_]*=", line)
    ]
    overrides = dotenv_values(stream=io.StringIO("\n".join(lines)))
    documented = Settings.model_validate({**defaults.model_dump(), **overrides})
    keys = {
        key
        for key in Settings.model_fields
        if key.startswith(("CORS_", "HTTP_", "REQUEST_", "RATE_LIMIT_"))
        or key == "TRUST_PROXY"
    }

    assert keys <= overrides.keys()
    assert all(getattr(documented, key) == getattr(defaults, key) for key in keys)


OPERATIONAL_FLAGS = ("DOCS_ENABLED", "DIAGNOSTICS_ENABLED", "METRICS_ENABLED")


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_operational_defaults_follow_environment(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    result = settings(monkeypatch, ENV=environment)

    assert all(
        getattr(result, key) is (environment != "production")
        for key in OPERATIONAL_FLAGS
    )


@pytest.mark.parametrize("environment", ["development", "test", "production"])
@pytest.mark.parametrize("key", OPERATIONAL_FLAGS)
@pytest.mark.parametrize("value", ["true", "false"])
def test_independent_operational_overrides(
    monkeypatch: pytest.MonkeyPatch, environment: str, key: str, value: str
) -> None:
    result = settings(monkeypatch, ENV=environment, **{key: value})

    assert getattr(result, key) is (value == "true")
    assert all(
        getattr(result, other) is (environment != "production")
        for other in OPERATIONAL_FLAGS
        if other != key
    )


@pytest.mark.parametrize("key", OPERATIONAL_FLAGS)
@pytest.mark.parametrize("value", ["", "TRUE", "False", "1", "yes", " true "])
def test_operational_overrides_reject_ambiguous_values(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        settings(monkeypatch, **{key: value})


@pytest.mark.parametrize("key", OPERATIONAL_FLAGS)
def test_explicit_null_is_not_an_operational_default(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    values = settings(monkeypatch).model_dump()

    with pytest.raises(ValidationError):
        Settings.model_validate({**values, key: None})


RATE_NUMBERS = {
    "RATE_LIMIT_WINDOW_MS": (60000, 1, 86400000),
    "RATE_LIMIT_MAX": (200, 1, 10000),
    "RATE_LIMIT_MAX_CLIENTS": (10000, 1, 100000),
}


def test_rate_limit_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    result = settings(monkeypatch)

    assert all(
        getattr(result, key) == default for key, (default, _, _) in RATE_NUMBERS.items()
    )


@pytest.mark.parametrize("key", RATE_NUMBERS)
@pytest.mark.parametrize(
    "value", ["", " ", "0", "-1", "1.5", "NaN", "Infinity", "true", "1e3"]
)
def test_rate_limit_invalid_values(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        settings(monkeypatch, **{key: value})


@pytest.mark.parametrize("key", RATE_NUMBERS)
def test_rate_limit_boundaries(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    _, lower, upper = RATE_NUMBERS[key]
    base = {"RATE_LIMIT_MAX": "1", "RATE_LIMIT_MAX_CLIENTS": "1"}

    for value in [lower, upper]:
        assert getattr(settings(monkeypatch, **{**base, key: str(value)}), key) == value

    with pytest.raises(ValidationError):
        settings(monkeypatch, **{**base, key: str(upper + 1)})


@pytest.mark.parametrize("value", [True, 1.5, float("nan"), float("inf")])
@pytest.mark.parametrize("key", RATE_NUMBERS)
def test_rate_limit_python_types_are_strict(
    monkeypatch: pytest.MonkeyPatch, key: str, value: object
) -> None:
    values = settings(monkeypatch).model_dump()

    with pytest.raises(ValidationError):
        Settings.model_validate({**values, key: value})


def test_rate_limit_combined_storage_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        settings(
            monkeypatch, RATE_LIMIT_MAX="10000", RATE_LIMIT_MAX_CLIENTS="200"
        ).RATE_LIMIT_MAX_CLIENTS
        == 200
    )
    with pytest.raises(ValidationError):
        settings(monkeypatch, RATE_LIMIT_MAX="201", RATE_LIMIT_MAX_CLIENTS="10000")
