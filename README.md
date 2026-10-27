# QuickAPI-FastAPI

A FastAPI reference service with one CRUD items resource, async SQLAlchemy persistence, transport middleware, and operational diagnostics.

The small domain keeps the focus on application boundaries, failure handling, and automated checks. Authentication and authorization are outside the template's scope; deployment readiness depends on the consuming service's trust boundary, database, and operations.

## What's included

- Pydantic request/response models and a shared JSON error envelope.
- Request-owned database sessions and repository-owned mutations with rollback.
- Pure-ASGI middleware for request context, logging, CORS, security headers, limits, timeouts, rate limiting, and Prometheus metrics.
- Managed startup/shutdown, separate liveness/readiness probes, and system diagnostics.
- Unit, integration, and in-process HTTP E2E suites, plus CI checks of the built container.

## Getting started

Use Python 3.12. Docker Engine is needed for container verification.

1. Create a Python 3.12 virtual environment (`py -3.12 -m venv .venv` on Windows or `python3.12 -m venv .venv` on Linux/macOS), activate it, then run `python -m pip install -r requirements-dev.txt` and `python -m pip check`.
2. Copy [.env.example](.env.example) to a gitignored `.env`.
3. Set `DATABASE_URL` to a reachable MySQL instance using `mysql+asyncmy://...`, or use `sqlite+aiosqlite:///./app.db` for a self-contained local run.
4. Run `python -m app.main`.

The example binds port **5000**. Swagger UI is at `/docs`, ReDoc at `/redoc`, and OpenAPI JSON at `/openapi.json`. See [Development](docs/development.md) for shell-specific commands and configuration.

## Documentation

| Guide | Contents |
| --- | --- |
| [Development](docs/development.md) | Setup, configuration, database selection, and local commands |
| [Architecture](docs/architecture.md) | Folder boundaries, middleware order, lifecycle, and transactions |
| [API contracts](docs/api-contracts.md) | Item routes, validation, pagination, errors, and API extension rules |
| [Request deadlines](docs/request-timeouts.md) | Timeout, streaming, disconnect, and cleanup behavior |
| [Testing](docs/testing.md) | Test layers, isolation, coverage gates, CI, and verification limits |
| [Deployment and operations](docs/deployment.md) | Container commands, probes, diagnostics, persistence, and recovery |
| [Technical backlog](docs/backlog.md) | Confirmed gaps and deliberately deferred work |

See the [Express parity roadmap](docs/roadmap.md) and [milestone list](docs/milestones.md) for phased repairs, MySQL/migration work, API alignment, and production/release verification. Phase 1A results are recorded in [Verification](docs/verification.md).

Configuration examples live in [.env.example](.env.example), validation in [app/config/environment.py](app/config/environment.py), dependencies in [requirements.txt](requirements.txt), and CI commands in [.github/workflows/tests.yml](.github/workflows/tests.yml).

## API overview

| Surface | Routes |
| --- | --- |
| Items | `/api/v1/items/` and `/api/v1/items/{id}` |
| Liveness and readiness | `/health` and `/ready` |
| Runtime diagnostics | `/info` and `/system` |
| Prometheus metrics | `/metrics` |

Routes currently have no application authentication. This service does not implement the account, article, or authorization contracts of QuickAPI-NestJS.

## Quality checks

```sh
python -m black --check app tests
python -m ruff check app tests
python -m mypy app
python -m pytest -q
```

Follow [Testing](docs/testing.md) for layer selection, critical coverage thresholds, and container checks. SQLite-backed tests and a container smoke test do not establish production MySQL or deployment readiness.

## License

[MIT](LICENSE).
