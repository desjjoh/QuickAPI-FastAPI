import sys

import uvicorn

from app.config.environment import settings

red = "\033[91m"
bold = "\033[1m"


def main() -> None:
    uvicorn.run(
        "app.config.application:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENV == "development"),
        log_config=None,
        # The app owns proxy trust; never let Uvicorn apply a second policy.
        proxy_headers=False,
    )


def run() -> None:
    """Start the server, converting fatal initialization errors to an exit code."""
    try:
        main()

    except Exception:
        print(
            f"{red}❌ {bold}Fatal error during server initialization — forcing exit\n"
        )

        sys.exit(1)


if __name__ == "__main__":
    run()
