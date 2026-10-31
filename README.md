# QuickAPI-FastAPI

A FastAPI reference service with one CRUD items resource, async SQLAlchemy persistence, transport middleware, and operational diagnostics.

The small domain keeps the focus on application boundaries, failure handling, and automated checks. Authentication and authorization are outside the template's scope; deployment readiness depends on the consuming service's trust boundary, database, and operations.

## What's included

- Pydantic request/response models and a shared JSON error envelope.
- Request-owned mutation transactions covering persistence and response preparation.
- Pure-ASGI middleware for request context, logging, CORS, security headers, limits, timeouts, rate limiting, and Prometheus metrics.
- Managed startup/shutdown, separate liveness/readiness probes, and system diagnostics.
- Unit, integration, and in-process HTTP E2E suites, plus CI checks of the built container.

## Getting started

Use Python 3.12. Docker Engine and Compose v2 are required for the default MySQL setup and container verification.

1. Create a Python 3.12 virtual environment (`py -3.12 -m venv .venv` on Windows or `python3.12 -m venv .venv` on Linux/macOS), activate it, then run `python -m pip install -r requirements-dev.txt` and `python -m pip check`.
2. Copy [.env.example](.env.example) to a gitignored `.env`.
3. Start local MySQL with `docker compose up -d --wait mysql`. The example `DATABASE_URL` reaches the isolated `quickapi-fastapi-dev` database at `127.0.0.1:3310`. Run `python -m alembic upgrade head` before starting the API. See [Migrations](docs/setup.md#database-migrations) for the command guide.
4. Run `python -m app.main`.

For the complete local container stack, run `docker compose up --build -d --wait`; the container API is at `http://127.0.0.1:8000`. Compose overrides the native database URL, bind address, port, and mode for its internal topology. See [local Compose](docs/setup.md#local-compose).

The native Python example binds port **8000**. When `DOCS_ENABLED` is enabled, Swagger UI is at `/docs`, ReDoc at `/redoc`, and OpenAPI JSON at `/openapi.json`. See [Setup](docs/setup.md#prerequisites-and-native-startup) for shell-specific commands and configuration.

## Documentation

| Guide                                  | Contents                                                                                  |
| -------------------------------------- | ----------------------------------------------------------------------------------------- |
| [Setup](docs/setup.md)                 | Python environment, local Compose, dependencies, migrations, and formatting               |
| [Architecture](docs/architecture.md)   | Layers, routing, middleware, API contracts, transactions, replay, and database lifecycle  |
| [Configuration](docs/configuration.md) | Environment sources, validation, transport, database, exposure, and replay settings       |
| [Testing](docs/testing.md)             | Test layers, disposable database safety, coverage, CI, and required-check boundaries      |
| [Security](docs/security.md)           | Public API access, proxy/CORS trust, operational exposure, rate limits, and scan policies |
| [Deployment](docs/deployment.md)       | Images, operations, deadlines, shutdown, releases, and rollback                           |
| [Backlog](docs/backlog.md)             | Unresolved qualification and deferred capabilities                                        |

Configuration examples live in [.env.example](.env.example), validation in [app/config/environment.py](app/config/environment.py), dependencies in [requirements.txt](requirements.txt), and CI commands in [.github/workflows/tests.yml](.github/workflows/tests.yml).

## API overview

| Surface                | Routes                                   |
| ---------------------- | ---------------------------------------- |
| Items                  | `/api/v1/items` and `/api/v1/items/{id}` |
| Liveness and readiness | `/health` and `/ready`                   |
| Runtime diagnostics    | `/info` and `/system`                    |
| Prometheus metrics     | `/metrics`                               |

The item API has no application authentication or authorization.

## Quality checks

```sh
python -m scripts.format_code --check
python -m ruff check app tests scripts
python -m mypy app scripts
python -m pytest -q -m unit --no-cov
```

Run `python -m scripts.test_db test` for managed disposable-MySQL setup, full-suite
coverage, and cleanup. Direct persistence pytest runs require prepared infrastructure.
See [Testing](docs/testing.md) for commands, isolation, and CI boundaries; automated
checks do not establish deployed ingress, backup restoration, or provider behavior.

## License

[MIT](LICENSE).
