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

Use Python 3.12. Docker Engine is needed for container verification.

1. Create a Python 3.12 virtual environment (`py -3.12 -m venv .venv` on Windows or `python3.12 -m venv .venv` on Linux/macOS), activate it, then run `python -m pip install -r requirements-dev.txt` and `python -m pip check`.
2. Copy [.env.example](.env.example) to a gitignored `.env`.
3. Start local MySQL with `docker compose up -d --wait mysql`. The example `DATABASE_URL` reaches the isolated `quickapi-fastapi-dev` database at `127.0.0.1:3310`. Run `python -m alembic upgrade head` before starting the API. See [Migrations](docs/migrations.md) for the command guide.
4. Run `python -m app.main`.

For the complete local container stack, run `docker compose up --build -d --wait`; the container API is at `http://127.0.0.1:8000`. Compose overrides the native database URL, bind address, port, and mode for its internal topology. See [local Compose](docs/development.md#local-compose).

The native Python example binds port **8000**. When `DOCS_ENABLED` is enabled, Swagger UI is at `/docs`, ReDoc at `/redoc`, and OpenAPI JSON at `/openapi.json`. See [Development](docs/development.md) for shell-specific commands and configuration.

## Documentation

| Guide | Contents |
| --- | --- |
| [Development](docs/development.md) | Setup, configuration, database selection, and local commands |
| [Architecture](docs/architecture.md) | Folder boundaries, middleware order, lifecycle, and transactions |
| [Controllers and services](docs/services.md) | Controller response validation, service-owned logic, dependency injection, and session ownership |
| [Python formatting](docs/formatting.md) | Logical spacing, Black, format-on-save, CLI commands and CI enforcement |
| [API contracts](docs/api-contracts.md) | Item routes, validation, pagination, errors, and API extension rules |
| [Item API specification](docs/item-contract-specification.md) | Agreed Express contract for item alignment and compatibility decisions |
| [Database settings](docs/database-settings.md) | Connection/queue limits, deadlines, TLS, and transport tests |
| [Mutation transactions](docs/transactions.md) | Decorator, session ownership, response preparation, and rollback boundaries |
| [Durable mutation retries](docs/idempotency.md) | Idempotency keys, replay, shared domain policies and cleanup |
| [Graceful shutdown](docs/shutdown.md) | Request draining, cleanup order, shutdown budgets, and process tests |
| [Database readiness and recovery](docs/database-lifecycle.md) | Shared probes, startup verification, outages, and connection cleanup |
| [MySQL testing](docs/mysql-testing.md) | Disposable test infrastructure, .env.test, migrations, and CI |
| [Migrations](docs/migrations.md) | Database setup, Alembic commands, schema checks, and disposable resets |
| [Logging](docs/logging.md) | Console/JSON output, levels, request correlation, and safe diagnostics |
| [Rate limiting](docs/rate-limiting.md) | Bounded rolling windows, storage capacity, retry timing, and probe policy |
| [Operational exposure](docs/operational-exposure.md) | Docs/diagnostic/metrics flags, production defaults, and minimal probes |
| [HTTP configuration](docs/http-policy.md) | Defaults, env overrides, CORS, proxy trust, and request budgets |
| [Request deadlines](docs/request-timeouts.md) | Timeout, streaming, disconnect, and cleanup behavior |
| [Testing](docs/testing.md) | Test layers, isolation, coverage gates, CI, and verification limits |
| [Branch protections](docs/branch-protection.md) | Major-branch policy, check contexts, and required-check configuration |
| [Deployment and operations](docs/deployment.md) | Container commands, probes, diagnostics, persistence, and recovery |
| [Milestones](docs/milestones.md) | Implementation scope, status and deferred work |

Implementation scope, status and outstanding work are maintained in [Milestones](docs/milestones.md). Dated execution evidence is recorded in [Verification](docs/verification.md).

Configuration examples live in [.env.example](.env.example), validation in [app/config/environment.py](app/config/environment.py), dependencies in [requirements.txt](requirements.txt), and CI commands in [.github/workflows/tests.yml](.github/workflows/tests.yml).

## API overview

| Surface | Routes |
| --- | --- |
| Items | `/api/v1/items/` and `/api/v1/items/{id}` |
| Liveness and readiness | `/health` and `/ready` |
| Runtime diagnostics | `/info` and `/system` |
| Prometheus metrics | `/metrics` |

Routes have no application authentication. This service does not implement the account, article, or authorization contracts of QuickAPI-NestJS.

## Quality checks

```sh
python -m scripts.format_code --check
python -m ruff check app tests scripts
python -m mypy app scripts
python -m pytest -q
```

Follow [Testing](docs/testing.md) for layer selection, critical coverage thresholds, and container checks. All persistence and coverage runs use disposable MySQL. The built-image check uses an independent disposable MySQL server. See [MySQL testing](docs/mysql-testing.md) for the test runner. These checks do not establish deployment readiness.

## License

[MIT](LICENSE).
