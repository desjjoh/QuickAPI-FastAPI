import logging
import os
import socket
from typing import Any, Protocol, cast, runtime_checkable

import structlog
from colorama import Fore, Style
from structlog.typing import EventDict, WrappedLogger

from app.config.environment import settings

colors: dict[str, str] = {
    "DEBUG": Fore.CYAN,
    "INFO": Fore.GREEN,
    "WARNING": Fore.YELLOW,
    "ERROR": Fore.RED,
    "CRITICAL": Fore.MAGENTA,
}

LOG_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
}

dark_green = '\x1b[2m\x1b[32m'
reset: str = Style.RESET_ALL


def add_process_context(
    _: WrappedLogger,
    __: str,
    event_dict: EventDict,
) -> EventDict:
    event_dict["pid"] = os.getpid()
    event_dict["hostname"] = socket.gethostname()

    return event_dict


@runtime_checkable
class LoggerProtocol(Protocol):
    def debug(self, event: str, **kwargs: Any) -> None: ...
    def info(self, event: str, **kwargs: Any) -> None: ...
    def warning(self, event: str, **kwargs: Any) -> None: ...
    def error(self, event: str, **kwargs: Any) -> None: ...
    def critical(self, event: str, **kwargs: Any) -> None: ...


logging.basicConfig(format="%(message)s", level=logging.DEBUG)

for noisy in (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "fastapi",
    "asyncmy",
):
    logging.getLogger(noisy).handlers = []
    logging.getLogger(noisy).propagate = False
    logging.getLogger(noisy).setLevel(logging.CRITICAL)


def concise_renderer(_: WrappedLogger, __: str, event_dict: EventDict) -> str:
    timestamp = event_dict.pop("timestamp", "")[:-3]
    level = event_dict.pop("level", "")
    message = event_dict.pop("event", "")
    request_id = event_dict.pop("request_id", None)
    pid = event_dict.pop("pid", None)

    line: str = f"{dark_green}{timestamp}{reset}"

    if pid:
        line += f" {Fore.CYAN}[{pid}]{reset}"

    color: str = colors.get(level.upper(), Fore.WHITE)

    line += f" {color}[{level.ljust(8)}]{reset}"

    if request_id:
        line += f" {Fore.MAGENTA}[{request_id}]{reset}"

    line += f" {message}"

    return line


structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        add_process_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f", utc=False),
        concise_renderer,
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        LOG_LEVEL_MAP.get(settings.LOG_LEVEL, logging.INFO)
    ),
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)


class _LogProxy(LoggerProtocol):
    def __getattribute__(self, name: str):
        logger = structlog.get_logger()
        return getattr(logger, name)

    def debug(self, event: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def info(self, event: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def warning(self, event: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def error(self, event: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def critical(self, event: str, **kwargs: Any) -> None:
        raise NotImplementedError


log: LoggerProtocol = cast(LoggerProtocol, _LogProxy())
