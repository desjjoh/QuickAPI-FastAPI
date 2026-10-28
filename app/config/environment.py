import json
import os
import re
import sys
from datetime import UTC, datetime
from typing import Annotated, Literal, NoReturn, Self, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values
from pydantic import (
    AnyHttpUrl,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import ErrorDetails
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.config.http_policy import FORBIDDEN_HEADERS, HTTP_METHODS, proxy_network
from app.config.rate_limit_policy import (
    DEFAULT_MAX_CLIENTS,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_WINDOW_MS,
    ClientCapacity,
    RateLimitPolicy,
    RequestCapacity,
    WindowMilliseconds,
)

StringList = Annotated[list[str], NoDecode]

SEMVER_REGEX = r"^\d+\.\d+\.\d+$"
DEFAULT_API_PUBLISHED_PORT = 8000
DEFAULT_MYSQL_PUBLISHED_PORT = 3308


def operational_default(data: dict[str, object]) -> bool:
    return data.get("ENV") != "production"


class Settings(BaseSettings):
    APP_NAME: str = Field(..., min_length=1, max_length=120)
    APP_VERSION: str = Field(..., pattern=SEMVER_REGEX)

    ENV: Literal["development", "production", "test"]
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARN", "ERROR"] = "INFO"

    HOST: str = "0.0.0.0"
    PORT: int = Field(..., ge=1, le=65_535)
    API_PUBLISHED_PORT: int = Field(DEFAULT_API_PUBLISHED_PORT, ge=1, le=65_535)
    MYSQL_PUBLISHED_PORT: int = Field(DEFAULT_MYSQL_PUBLISHED_PORT, ge=1, le=65_535)

    DATABASE_URL: str = Field(..., min_length=5)
    TIMEZONE: str = "Etc/UTC"

    # Operational routes default on in development/test, off in production.
    DOCS_ENABLED: bool = Field(default_factory=operational_default)
    DIAGNOSTICS_ENABLED: bool = Field(default_factory=operational_default)
    METRICS_ENABLED: bool = Field(default_factory=operational_default)

    # Defaults live here; .env and process environment optionally override them.
    CORS_ORIGINS: StringList = Field(
        default_factory=lambda: ["http://localhost:3000"], min_length=1, max_length=100
    )
    CORS_METHODS: StringList = Field(
        default_factory=lambda: [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "HEAD",
            "OPTIONS",
        ],
        min_length=1,
        max_length=7,
    )
    CORS_ALLOWED_HEADERS: StringList = Field(
        default_factory=lambda: ["content-type", "authorization", "x-requested-with"],
        max_length=100,
    )
    CORS_EXPOSED_HEADERS: StringList = Field(
        default_factory=lambda: ["authorization", "set-cookie"], max_length=100
    )
    CORS_CREDENTIALS: bool = True
    CORS_MAX_AGE_SECONDS: int = Field(86_400, ge=0, le=86_400)
    TRUST_PROXY: StringList = Field(default_factory=list, max_length=100)

    RATE_LIMIT_WINDOW_MS: WindowMilliseconds = DEFAULT_WINDOW_MS
    RATE_LIMIT_MAX: RequestCapacity = DEFAULT_MAX_REQUESTS
    RATE_LIMIT_MAX_CLIENTS: ClientCapacity = DEFAULT_MAX_CLIENTS

    REQUEST_TIMEOUT_MS: int = Field(10_000, ge=1, le=2_147_483_647)
    REQUEST_FIRST_BODY_TIMEOUT_MS: int = Field(5_000, ge=1, le=2_147_483_647)
    REQUEST_CHUNK_TIMEOUT_MS: int = Field(2_000, ge=1, le=2_147_483_647)
    HTTP_MAX_BODY_BYTES: int = Field(1_048_576, ge=1, le=1_073_741_824)
    HTTP_MAX_HEADER_COUNT: int = Field(100, ge=1, le=10_000)
    HTTP_MAX_SINGLE_HEADER_BYTES: int = Field(4_096, ge=1, le=1_048_576)
    HTTP_MAX_TOTAL_HEADER_BYTES: int = Field(8_192, ge=1, le=16_777_216)
    HTTP_ALLOWED_METHODS: StringList = Field(
        default_factory=lambda: [
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "HEAD",
            "OPTIONS",
        ],
        min_length=1,
        max_length=7,
    )
    HTTP_ALLOWED_CONTENT_TYPES: StringList = Field(
        default_factory=lambda: ["application/json", "multipart/form-data"],
        min_length=1,
        max_length=100,
    )

    @field_validator(
        "CORS_ORIGINS",
        "CORS_METHODS",
        "CORS_ALLOWED_HEADERS",
        "CORS_EXPOSED_HEADERS",
        "TRUST_PROXY",
        "HTTP_ALLOWED_METHODS",
        "HTTP_ALLOWED_CONTENT_TYPES",
        mode="before",
    )
    @classmethod
    def parse_list(cls, value: object) -> object:
        if isinstance(value, str):
            value = [] if not value.strip() else value.split(",")
        if not isinstance(value, list):
            raise ValueError("must be a comma-separated list")
        items: list[str] = []
        for entry in cast(list[object], value):
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("list entries must be non-empty strings")
            entry = entry.strip()
            if entry not in items:
                items.append(entry)
        return items

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = AnyHttpUrl(value)
            # Match the browser's serialized origin, including normalized host/port.
            if (
                str(parsed).removesuffix("/") != value
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path != "/"
                or parsed.query is not None
                or parsed.fragment is not None
                or parsed.port == 0
                or "*" in value
            ):
                raise ValueError(
                    "use exact HTTP(S) origins without paths, credentials, queries, fragments, or wildcards"
                )
        return values

    @field_validator("CORS_METHODS", "HTTP_ALLOWED_METHODS")
    @classmethod
    def validate_methods(cls, values: list[str]) -> list[str]:
        if any(value not in HTTP_METHODS for value in values):
            raise ValueError("use uppercase supported HTTP methods")
        return values

    @field_validator("CORS_ALLOWED_HEADERS", "CORS_EXPOSED_HEADERS")
    @classmethod
    def validate_headers(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.lower() for value in values))
        if any(
            not re.fullmatch(r"[a-z0-9-]+", value)
            or value in FORBIDDEN_HEADERS
            or value == "connection"
            for value in normalized
        ):
            raise ValueError(
                "use supported HTTP header names; forwarding/hop-by-hop headers are reserved"
            )
        return normalized

    @field_validator("HTTP_ALLOWED_CONTENT_TYPES")
    @classmethod
    def validate_content_types(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.lower() for value in values))
        if any(
            not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", value)
            for value in normalized
        ):
            raise ValueError("use exact media types without parameters or wildcards")
        return normalized

    @field_validator("TRUST_PROXY")
    @classmethod
    def validate_proxies(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(proxy_network(value)) for value in values))

    @field_validator(
        "CORS_CREDENTIALS",
        "DOCS_ENABLED",
        "DIAGNOSTICS_ENABLED",
        "METRICS_ENABLED",
        mode="before",
    )
    @classmethod
    def strict_boolean(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError("must be true or false")

    @field_validator(
        "RATE_LIMIT_WINDOW_MS",
        "RATE_LIMIT_MAX",
        "RATE_LIMIT_MAX_CLIENTS",
        "REQUEST_TIMEOUT_MS",
        "REQUEST_FIRST_BODY_TIMEOUT_MS",
        "REQUEST_CHUNK_TIMEOUT_MS",
        "HTTP_MAX_BODY_BYTES",
        "HTTP_MAX_HEADER_COUNT",
        "HTTP_MAX_SINGLE_HEADER_BYTES",
        "HTTP_MAX_TOTAL_HEADER_BYTES",
        "CORS_MAX_AGE_SECONDS",
        mode="before",
    )
    @classmethod
    def strict_integer(cls, value: object) -> object:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            return value
        raise ValueError("must be a whole number within the documented range")

    @model_validator(mode="after")
    def validate_http_relationships(self) -> Self:
        if self.HTTP_MAX_SINGLE_HEADER_BYTES > self.HTTP_MAX_TOTAL_HEADER_BYTES:
            raise ValueError(
                "HTTP_MAX_SINGLE_HEADER_BYTES must not exceed HTTP_MAX_TOTAL_HEADER_BYTES"
            )
        if (
            max(self.REQUEST_FIRST_BODY_TIMEOUT_MS, self.REQUEST_CHUNK_TIMEOUT_MS)
            > self.REQUEST_TIMEOUT_MS
        ):
            raise ValueError("body wait deadlines must not exceed REQUEST_TIMEOUT_MS")
        if not set(self.CORS_METHODS).issubset(self.HTTP_ALLOWED_METHODS):
            raise ValueError("CORS_METHODS must be a subset of HTTP_ALLOWED_METHODS")
        RateLimitPolicy(
            window_ms=self.RATE_LIMIT_WINDOW_MS,
            max_requests=self.RATE_LIMIT_MAX,
            max_clients=self.RATE_LIMIT_MAX_CLIENTS,
        )
        return self

    @field_validator("API_PUBLISHED_PORT", "MYSQL_PUBLISHED_PORT", mode="before")
    @classmethod
    def validate_published_port(cls, value: object, info: ValidationInfo) -> object:
        if value == "":
            return (
                DEFAULT_API_PUBLISHED_PORT
                if info.field_name == "API_PUBLISHED_PORT"
                else DEFAULT_MYSQL_PUBLISHED_PORT
            )
        if isinstance(value, str):
            if value.isascii() and value.isdecimal():
                return value
        elif isinstance(value, int) and not isinstance(value, bool):
            return value
        raise ValueError("must be an integer port from 1 through 65535")

    @field_validator("TIMEZONE")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Accept only identifiers supplied by the system IANA timezone database."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("must be a valid IANA timezone identifier") from exc
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        validate_default=True,
        extra="ignore",
    )


def load_settings() -> Settings:
    try:
        return Settings()  # type: ignore

    except ValidationError as err:
        print_env_error_and_exit(err)
        sys.exit(1)


def print_env_error_and_exit(err: ValidationError) -> NoReturn:
    red = "\033[91m"
    reset = "\033[0m"
    yellow = "\033[93m"
    dark_green = '\x1b[2m\x1b[32m'

    errors: list[ErrorDetails] = err.errors()

    loc_names: list[str] = [
        ".".join(str(x) for x in issue.get("loc", [])) or "configuration"
        for issue in errors
    ]
    mode = os.environ.get("ENV")
    if mode is None:
        mode = dotenv_values(".env").get("ENV")
    if mode == "production":
        print(
            json.dumps(
                {
                    "time": datetime.now(UTC)
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z"),
                    "levelLabel": "critical",
                    "msg": "Environment validation failed.",
                    "fields": loc_names,
                }
            )
        )
        sys.exit(1)

    print(f"\n{red}Environment validation failed! ({len(errors)} issues){reset}\n")
    max_len: int = max(len(name) for name in loc_names)

    for name in loc_names:
        print(
            f"  - {yellow}{name.ljust(max_len)}{reset}  - Invalid or missing configuration value."
        )

    print(f"\n{dark_green}Fix the fields above and restart the application...{reset}\n")
    sys.exit(1)


settings: Settings = load_settings()
