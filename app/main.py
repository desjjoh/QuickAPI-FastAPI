import sys

import uvicorn

from app.config.environment import settings
from app.config.logging import log


def main() -> None:
    uvicorn.run(
        "app.config.application:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENV == "development"),
        loop="app.config.event_loop:server_loop_factory",
        log_config=None,
        # The app owns proxy trust; never let Uvicorn apply a second policy.
        proxy_headers=False,
    )


def run() -> None:
    """Start the server, converting fatal initialization errors to an exit code."""
    try:
        main()

    except Exception as exc:
        log.critical("Fatal error during server initialization.", error=exc)
        sys.exit(1)


if __name__ == "__main__":
    run()
