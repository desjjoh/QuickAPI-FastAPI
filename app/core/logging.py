import logging
import structlog
from colorama import Fore, Style
from app.core.config import settings


def setup_logging() -> None:
    logging.basicConfig(format="%(message)s", level=logging.INFO)

    COLORS = {
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "DEBUG": Fore.CYAN,
    }

    def concise_renderer(_: dict, __: str, event_dict: dict) -> str:
        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "").upper()
        message = event_dict.pop("event", "")
        extras = " ".join(f'"{k}":{repr(v)}' for k, v in event_dict.items())

        color = COLORS.get(level, Fore.WHITE)
        message_color = Fore.CYAN
        reset = Style.RESET_ALL

        return (
            f"[{timestamp}]{reset} "
            f"{color}{level:<5}{reset}: "
            f"{message_color}{message}{reset} "
            f"{Style.DIM}{{{extras}}}{reset}"
        )

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S.%f", utc=False),
            concise_renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()
