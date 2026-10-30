import sys
from pathlib import Path

import uvicorn
from uvicorn.supervisors import ChangeReload

from app.common.handlers.http_server import ApplicationServer
from app.config.environment import settings
from app.config.logging import log


def main() -> None:
    config = uvicorn.Config(
        "app.config.application:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENV == "development"),
        reload_dirs=(
            [str(Path(__file__).resolve().parent)]
            if settings.ENV == "development"
            else None
        ),
        ws="none",
        loop="app.config.event_loop:server_loop_factory",
        log_config=None,
        # The app owns proxy trust; never let Uvicorn apply a second policy.
        proxy_headers=False,
    )
    server = ApplicationServer(config)

    if config.should_reload:
        sock = config.bind_socket()

        ChangeReload(config, target=server.run, sockets=[sock]).run()
    else:
        server.run()


def run() -> None:
    """Start the server, converting fatal initialization errors to an exit code."""
    try:
        main()

    except Exception as exc:
        log.critical("Fatal error during server initialization.", error=exc)
        sys.exit(1)


if __name__ == "__main__":
    run()
