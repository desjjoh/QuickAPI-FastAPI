import sys
from typing import Literal, NoReturn
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator
from pydantic_core import ErrorDetails
from pydantic_settings import BaseSettings, SettingsConfigDict

SEMVER_REGEX = r"^\d+\.\d+\.\d+$"


class Settings(BaseSettings):
    APP_NAME: str = Field(..., min_length=1, max_length=120)
    APP_VERSION: str = Field(..., pattern=SEMVER_REGEX)

    ENV: Literal["development", "production", "test"]
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARN", "ERROR"] = "INFO"

    HOST: str = "0.0.0.0"
    PORT: int = Field(..., ge=1, le=65_535)

    DATABASE_URL: str = Field(..., min_length=5)
    TIMEZONE: str = "Etc/UTC"

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
    bold = "\033[1m"
    yellow = "\033[93m"
    dark_green = '\x1b[2m\x1b[32m'

    errors: list[ErrorDetails] = err.errors()

    print(
        f"\n{red}❌ {bold}Environment validation failed! ({len(errors)} issues){reset}\n"
    )

    loc_names: list[str] = [
        ".".join(str(x) for x in issue.get("loc", [])) for issue in errors
    ]
    max_len: int = max(len(name) for name in loc_names)

    for issue, name in zip(errors, loc_names):
        msg: str = issue.get("msg", "Invalid value")

        if issue.get("type") == "missing" or "input" not in issue:
            received_repr = "undefined"
        else:
            received_repr = repr(issue["input"])

        print(
            f"  - {yellow}{name.ljust(max_len)}{reset}  → "
            f"{msg}, (received: {red}{received_repr}{reset})"
        )

    print(f"\n{dark_green}Fix the fields above and restart the application…{reset}\n")
    sys.exit(1)


settings: Settings = load_settings()
