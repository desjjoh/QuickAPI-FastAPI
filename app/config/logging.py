"""Readable console logs and privacy-filtered production JSON."""

import json
import logging
import math
import os
import socket
import sys
from datetime import UTC, datetime
from typing import Any, Protocol, TextIO, cast

import structlog
from colorama import Fore, Style
from structlog.typing import EventDict, WrappedLogger

from app.common.helpers.error_diagnostics import error_diagnostics
from app.config.environment import settings

LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
}
colors = {
    "debug": Fore.CYAN,
    "info": Fore.GREEN,
    "warning": Fore.YELLOW,
    "error": Fore.RED,
    "critical": Fore.MAGENTA,
}
_FIELDS: dict[str, type | tuple[type, ...]] = {
    "requestId": str,
    "method": str,
    "ip": str,
    "route": str,
    "outcome": str,
    "headersSent": bool,
    "status": int,
    "durationMs": (int, float),
}


class LoggerProtocol(Protocol):
    def debug(self, event: str, **kwargs: Any) -> None: ...

    def info(self, event: str, **kwargs: Any) -> None: ...

    def warning(self, event: str, **kwargs: Any) -> None: ...

    def error(self, event: str, **kwargs: Any) -> None: ...

    def critical(self, event: str, **kwargs: Any) -> None: ...


def single_line(value: str) -> str:
    return "".join(
        (
            f"\\u{ord(char):04x}"
            if ord(char) < 32 or 127 <= ord(char) <= 159 or ord(char) in {8232, 8233}
            else char
        )
        for char in value
    )


def safe_event(_: WrappedLogger, method: str, event: EventDict) -> EventDict:
    record: EventDict = {
        "time": datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "levelLabel": method,
        "msg": (
            single_line(event["event"])
            if isinstance(event.get("event"), str)
            else "Application event."
        ),
    }

    if "requestId" not in event and "request_id" in event:
        event["requestId"] = event["request_id"]

    for key, expected in _FIELDS.items():
        value = event.get(key)

        if isinstance(value, expected) and not isinstance(value, BaseException):
            if isinstance(value, float) and not math.isfinite(value):
                continue

            record[key] = single_line(value) if isinstance(value, str) else value

    if record.get("method") not in {
        None,
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    }:
        record["method"] = "<other>"

    for alias in ("error", "err", "reason", "exception"):
        if alias in event:
            record["error" if alias == "exception" else alias] = error_diagnostics(
                event[alias]
            )

    return record


def concise_renderer(_: WrappedLogger, __: str, event: EventDict) -> str:
    level = event["levelLabel"]
    timestamp = (
        datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
        .astimezone()
        .strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    )
    reset = Style.RESET_ALL
    line = f"{Style.DIM}{Fore.GREEN}{timestamp}{reset} {Fore.CYAN}[{event['pid']}]{reset} {colors.get(level, Fore.WHITE)}[{level.ljust(8)}]{reset}"

    if event.get("requestId"):
        line += f" {Fore.MAGENTA}[{event['requestId']}]{reset}"

    return line + " " + cast(str, event["msg"])


class _Output:
    def write(self, value: str) -> int:
        try:
            return sys.stdout.write(value)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "utf-8"

            return sys.stdout.write(
                value.encode(encoding, errors="backslashreplace").decode(encoding)
            )

    def flush(self) -> None:
        sys.stdout.flush()


def create_logger(
    *,
    production: bool | None = None,
    level: str | None = None,
    stream: TextIO | None = None,
) -> LoggerProtocol:
    production = settings.ENV == "production" if production is None else production
    minimum = LOG_LEVEL_MAP[settings.LOG_LEVEL if level is None else level]
    renderer = (
        structlog.processors.JSONRenderer(
            serializer=json.dumps, ensure_ascii=True, allow_nan=False
        )
        if production
        else concise_renderer
    )

    return cast(
        LoggerProtocol,
        structlog.wrap_logger(
            structlog.PrintLogger(
                file=stream if stream is not None else cast(TextIO, _Output())
            ),
            processors=[structlog.contextvars.merge_contextvars, safe_event, renderer],
            wrapper_class=structlog.make_filtering_bound_logger(minimum),
            cache_logger_on_first_use=True,
        ),
    )


log = create_logger()


class SafeDependencyHandler(logging.Handler):
    """Never format dependency messages/arguments or expose their exception text."""

    def emit(self, record: logging.LogRecord) -> None:
        level = (
            "warning"
            if record.levelno == logging.WARNING
            else (
                "critical"
                if record.levelno >= logging.CRITICAL
                else (
                    "error"
                    if record.levelno >= logging.ERROR
                    else "info" if record.levelno >= logging.INFO else "debug"
                )
            )
        )
        fields: dict[str, object] = {}

        if record.exc_info and record.exc_info[1] is not None:
            fields["error"] = record.exc_info[1]

        getattr(log, level)(
            (
                "Server event."
                if record.name.startswith("uvicorn")
                else "Dependency log event."
            ),
            **fields,
        )


def configure_dependency_logging() -> None:
    # Application DEBUG output is independent of dependency verbosity. Enforce
    # the floor on the handler too: child loggers can set their own DEBUG level.
    minimum = max(logging.WARNING, LOG_LEVEL_MAP[settings.LOG_LEVEL])

    logging.captureWarnings(True)
    root = logging.getLogger()

    root.setLevel(minimum)
    handler = SafeDependencyHandler(level=minimum)
    root.handlers[:] = [handler]

    for name in (
        "uvicorn",
        "uvicorn.error",
        "fastapi",
        "asyncmy",
        "sqlalchemy",
        "httpx",
        "httpcore",
        "asyncio",
    ):
        logger = logging.getLogger(name)

        logger.handlers.clear()
        logger.propagate = True

        logger.setLevel(logging.WARNING)

    # Application request outcomes own access logging.
    access = logging.getLogger("uvicorn.access")

    access.handlers.clear()
    access.propagate = False

    access.addHandler(logging.NullHandler())


configure_dependency_logging()
