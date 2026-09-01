# QuickAPI-FastAPI

A production-oriented FastAPI reference service. Its deliberately small domain—one
CRUD `items` resource—keeps the focus on architecture, contracts, persistence,
runtime safety, testing, and deployment rather than feature count.

## What the repository proves

- Validated, environment-driven configuration with startup failure on invalid input.
- Pydantic request and response contracts plus one stable JSON error envelope.
- Async SQLAlchemy persistence with request-owned sessions and explicit transaction
  handling.
- A pure-ASGI middleware stack for request context, logging, CORS, security headers,
  size and header limits, timeouts, method/content-type enforcement, rate limiting,
  and Prometheus metrics.
- Managed application startup, health/readiness probes, and reverse-order shutdown.
- Unit, integration, and end-to-end suites with branch coverage and package-specific
  thresholds.
- CI gates for formatting, linting, typing, tests, coverage, container construction,
  and a smoke test of the built image.

Authentication and authorization are intentionally outside this template's scope.
Do not expose domain routes to untrusted clients without adding the trust boundary
appropriate to your application.

## Architecture

```text
app/
├── api/
│   ├── api_routes.py                 # top-level route composition
│   ├── system/                       # probes, diagnostics, metrics, metadata
│   └── v1/items/                     # item HTTP controllers and Pydantic models
├── common/
│   ├── docs/                         # OpenAPI contract customization
│   ├── handlers/                     # exception and lifecycle behavior
│   ├── middleware/                   # transport/security/observability policies
│   ├── models/                       # shared errors, parameters, pagination
│   └── store/                        # request context and rate-limit state
├── config/                           # app assembly, settings, DB, logging, metrics
├── database/
│   ├── entities/                     # SQLAlchemy mappings
│   └── repositories/                 # queries and transaction boundaries
├── public/                           # static assets
└── main.py                           # executable entry point
tests/
├── unit/                             # isolated behavior
├── integration/                      # real session/repository and app composition
└── e2e/                              # complete HTTP and lifespan behavior
```

Dependencies point inward: controllers depend on validated API models and the
repository abstraction; repositories own persistence operations; application
assembly is centralized in `app/config/application.py`. The domain is intentionally
not split into speculative service layers while it remains simple.

## Request lifecycle and middleware order

Starlette wraps middleware in reverse registration order. Consequently, the last
middleware added in `create_app()` is the first to see a request. The effective
inbound order is:

```text
cleanup → request context → request logging → CORS → security headers
→ body limit → content type → header sanitization → header limits
→ method allowlist → rate limit → timeout → metrics → routing/controller
```

Responses unwind through the same layers in reverse. This is intentional:

1. Cleanup is outermost so context variables are cleared even after failures.
2. Request identity is established before logging and returned as `X-Request-ID`.
3. Transport and security checks reject unsafe requests before domain code runs.
4. Timeout and metrics surround routed work so operational behavior is observable.
5. Controllers validate inputs, borrow a database session, call the repository, and
   serialize a declared response model.

Middleware rejections use the same error renderer as routed HTTP exceptions, so
clients do not need separate parsing behavior for transport and application errors.
The in-memory rate limiter is process-local by design; replace it with shared storage
before relying on a global limit across multiple workers or replicas.

## Application lifespan and operational endpoints

FastAPI's lifespan starts registered services before the app becomes ready. The
database service creates/checks its schema, readiness requires startup completion
and healthy registered services, and shutdown stops only successfully started
services in reverse order. Partial startup failure rolls back already-started
services. The unversioned operational surface is:

| Route          | Purpose                                                                 |
| -------------- | ----------------------------------------------------------------------- |
| `GET /`        | Friendly API greeting.                                                  |
| `GET /health`  | Process liveness only; it deliberately does not query dependencies.     |
| `GET /ready`   | Startup completion and health of every required registered service.     |
| `GET /info`    | Public application identity, process, Python, and platform metadata.    |
| `GET /system`  | Bounded host, process, event-loop, and database diagnostics.            |
| `GET /metrics` | Prometheus plaintext exposition using its full negotiated content type. |

Liveness and readiness are intentionally different. A failed liveness probe means
the process should be restarted. A failed readiness probe returns HTTP 503 and
means the running process should temporarily receive no application traffic. The
`database` entry in `ready.checks` is the registered database service's bounded
health check; it reports `up` only after startup and a successful database probe.
It is also summarized as `db` by `/system`.

Representative, contract-complete JSON responses are shown below (timestamps,
host values, timings, and resource measurements naturally vary):

**`GET /`:**

```json
{ "message": "Hello World! Welcome to FastAPI!" }
```

**`GET /health`:**

```json
{
  "alive": true,
  "status": "alive",
  "uptime": 123.45,
  "timestamp": "2026-09-01T12:00:00Z"
}
```

**`GET /ready`** (the same shape is returned with status 503 when not ready):

```json
{
  "ready": true,
  "status": "ready",
  "timestamp": "2026-09-01T12:00:00Z",
  "checks": [{ "name": "database", "status": "up", "response_time_ms": 1.2 }]
}
```

**`GET /info`:**

```json
{
  "name": "QuickAPI",
  "version": "1.0.0",
  "environment": "production",
  "hostname": "api-1",
  "pid": 42,
  "python_version": "3.12.1",
  "platform": "Linux",
  "architecture": "x86_64",
  "started_at": "2026-09-01T11:57:56Z",
  "timezone": "Etc/UTC"
}
```

**`GET /system`:**

```json
{
  "uptime": 123.45,
  "timestamp": 1788264000000,
  "event_loop_lag": 0.12,
  "db": "connected",
  "cpu": { "cores": 4, "model": "x86_64", "load_average": [0.1, 0.2, 0.3] },
  "memory": {
    "total_bytes": 8589934592,
    "available_bytes": 4294967296,
    "used_bytes": 4294967296,
    "percentage": 50.0
  },
  "process": {
    "rss_bytes": 67108864,
    "heap_total_bytes": 8388608,
    "heap_used_bytes": 4194304,
    "external_bytes": 0,
    "active_handles": 6
  },
  "os": { "platform": "Linux", "release": "6.8.0" }
}
```

`/metrics` is not JSON and declares no JSON schema. It returns Prometheus
plaintext with `CONTENT_TYPE_LATEST` (currently the complete media type
`text/plain; version=1.0.0; charset=utf-8`). For example:

```text
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/api/v1/items/",status="200"} 42
```

The Python diagnostics map platform facilities into stable API fields:

- `cpu.load_average` uses `os.getloadavg()` and falls back to three zeroes;
  `cpu.cores` uses `os.cpu_count()` with a floor of one, and absent identifiers
  become `unknown`.
- memory prefers Linux `/proc/meminfo`, then POSIX `os.sysconf()` page counters,
  and otherwise deterministically returns zero-valued byte counts and percentage.
- `process.rss_bytes` maps `resource.getrusage().ru_maxrss` to bytes (already bytes
  on macOS, KiB elsewhere); Python `tracemalloc` supplies the heap fields when
  enabled, `external_bytes` is always zero because Python has no portable mapping,
  and `active_handles` counts unfinished asyncio tasks.
- unavailable resource APIs, collection errors, or collection timeouts yield the
  documented non-negative zero/`unknown` fallbacks rather than an endpoint error.

Under the existing no-authentication policy these operational routes remain public.
Their payloads contain operational metadata but no credentials, connection strings,
environment-variable values, or other secrets. Apply a network trust boundary or
authentication before exposing them where host/process metadata is considered
sensitive.

Probe polling is not application traffic: Prometheus request middleware excludes
`/health`, `/ready`, `/info`, `/system`, and the existing `/metrics` scrape endpoint.
The greeting and versioned API routes remain instrumented. Metrics retain only the
established bounded `method`, normalized route `path`, and `status` labels; this
policy introduces no new or high-cardinality labels.

Run the targeted operational contract checks and then the complete suite with the
established commands:

```bash
pytest -q --no-cov tests/integration/errors/test_open_api.py
pytest -q --no-cov tests/unit/middleware/test_prometheus_metrics.py
pytest -q
```

## Configuration

Copy the example, then change values for the target environment:

```bash
cp .env.example .env
```

| Variable       | Requirement                                             |
| -------------- | ------------------------------------------------------- |
| `APP_NAME`     | Non-empty, at most 120 characters.                      |
| `APP_VERSION`  | Three-part semantic version such as `1.0.0`.            |
| `ENV`          | `development`, `test`, or `production`.                 |
| `LOG_LEVEL`    | `DEBUG`, `INFO`, `WARN`, or `ERROR`.                    |
| `HOST`         | Bind address; defaults to `0.0.0.0`.                    |
| `PORT`         | Integer from 1 through 65535.                           |
| `DATABASE_URL` | SQLAlchemy async URL; MySQL uses `mysql+asyncmy://...`. |

Pydantic validates configuration while importing the application. Missing or invalid
required values produce a field-by-field diagnostic and a non-zero exit rather than
starting a partially configured server. `.env` is for local development; deployment
systems should inject secrets and configuration instead of baking them into images.

## Persistence and migrations

`get_session()` creates one async session per dependency invocation and closes it
after the response dependency scope completes. Read queries do not commit. Each
repository mutation owns its transaction: it flushes and refreshes, commits on
success, and rolls back on any failure so the session is safe to close or reuse.

At startup, this reference currently calls SQLAlchemy `metadata.create_all()`. That
is deterministic for a fresh database but **is not a schema migration system** and
does not alter existing columns. Before evolving a deployed schema:

1. Add Alembic (or the migration system selected by the consuming service).
2. Generate a revision from the ORM metadata, inspect it, and test both upgrade and
   downgrade against the production database engine.
3. Run `alembic upgrade head` as a one-shot release task before rolling out the app.
4. Remove startup `create_all()` once migrations become authoritative.

This limitation is explicit so the template does not promise migration safety it
does not yet prove.

## Error contract

HTTP errors, validation failures, middleware rejections, and unhandled exceptions
share this response shape:

```json
{
  "status": 422,
  "message": "Validation failed: body.name → Field required.",
  "timestamp": 1764310185000
}
```

`status` is the HTTP status, `message` is safe client-facing text, and `timestamp`
is Unix time in milliseconds. Validation details are flattened into a deterministic
message; unhandled exceptions return only `Internal server error.` OpenAPI replaces
FastAPI's default validation schema with this contract.

## Run locally

Python 3.12 is the supported runtime.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

The example configuration binds port 5000. OpenAPI UI is available at `/docs`,
ReDoc at `/redoc`, and the item collection at `/api/v1/items/`.

## Quality gates and tests

Run the same static checks used by CI:

```bash
black --check app tests
ruff check app tests
mypy app
```

Every test has an explicit layer marker. CI first verifies that each layer collects
at least one test, preventing an accidentally empty suite from passing:

```bash
pytest --collect-only -q --no-cov -m unit
pytest --collect-only -q --no-cov -m integration
pytest --collect-only -q --no-cov -m e2e
pytest -q --no-cov -m unit
pytest -q --no-cov -m integration
pytest -q --no-cov -m e2e
```

The combined run enforces 90% statement and branch coverage. CI additionally
requires 90% middleware coverage and 95% coverage for lifecycle, database, and API
packages:

```bash
pytest -q
shopt -s globstar
coverage report --fail-under=90 app/common/middleware/*.py
coverage report --fail-under=95 app/common/handlers/lifecycle_handler.py
coverage report --fail-under=95 app/database/**/*.py
coverage report --fail-under=95 app/api/**/*.py
```

## Production container validation

Build and run the same immutable artifact CI smoke-tests:

```bash
docker build -t quickapi-fastapi:local .
docker run --rm -p 8000:8000 \
  -e APP_NAME=QuickAPI -e APP_VERSION=1.0.0 \
  -e ENV=production -e LOG_LEVEL=INFO \
  -e HOST=0.0.0.0 -e PORT=8000 \
  -e DATABASE_URL=sqlite+aiosqlite:////tmp/quickapi.db \
  quickapi-fastapi:local
curl --fail http://localhost:8000/ready
curl --fail http://localhost:8000/api/v1/items/
```

SQLite makes the smoke test self-contained; deploy with the async database URL and
durable database required by your service. `docker compose up --build` instead uses
the externally supplied `DATABASE_URL`. CI validates both startup readiness and a
real API request against the built runtime image—not merely that the Dockerfile
parses.

## License

MIT License — free for personal and commercial use.
