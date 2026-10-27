# Deployment and operations

[Documentation index](../README.md#documentation)

## Runtime configuration and access

Use Python 3.12 and inject required settings from [Development](development.md#configuration). The image installs runtime-only [requirements.txt](../requirements.txt), checks dependency consistency, and copies application code; `.env` is excluded. Development tools are installed separately from `requirements-dev.txt` for local/CI checks. Use `ENV=production` to disable reload and align listening/published ports and probes.

Domain, diagnostics, metrics, and API documentation endpoints have no application authentication. Apply the consuming service's network/authentication boundary. CORS currently allows all origins with credentials and is not a trust boundary. The rate limiter is process-local; workers/replicas do not share state.

## Production container validation

Build a local image using the same configuration pattern as CI. A local tag is not an immutable release reference:

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

SQLite makes the smoke test self-contained; `/tmp/quickapi.db` is disposable container storage. Deploy with the async database URL and durable storage required by your service. CI checks startup and an API read against the built image; it does not validate a production deployment or MySQL compatibility.

Run the container in one terminal and curl checks in a second. The example uses Bash continuation; use a single line or PowerShell continuation syntax in PowerShell.

## Local Compose topology

The checked-in [Compose file](../docker-compose.yaml) is a local development stack, not a hosted production deployment definition. It includes MySQL 8.4.6, a project-scoped persistent volume, an authenticated database health check, API startup ordering, and a health check on the API's fixed internal port 8000. Both API/database host ports are loopback-only and configurable. No fixed container names are shared with sibling apps.

Compose reads `.env` and overrides container-specific settings: `HOST=0.0.0.0`, `PORT=8000`, `ENV=production`, and a local MySQL service URL. Native Python keeps its own port/mode/database URL. The unused `DEBUG`/`WORKERS` entries were removed. See [local setup, credentials, persistence, and reset commands](development.md#local-compose).

A fresh disposable Compose project passed MySQL readiness, an API create/read, and record retention across container/network recreation with its volume preserved. This is local startup/persistence evidence, not a MySQL-backed release gate. CI's existing image smoke still uses SQLite; migration validation and production-like MySQL test/release qualification remain scheduled separately. See [Verification](verification.md).

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
The greeting and versioned API routes remain instrumented. Metrics currently label requests with `method`, raw URL `path`, and `status`.
Paths are not normalized to route templates: item IDs and unknown paths create
additional series. Cardinality remains an operational gap; see [Backlog](backlog.md).

Run the targeted operational contract checks and then the complete suite with the
established commands:

```bash
pytest -q --no-cov tests/integration/errors/test_open_api.py
pytest -q --no-cov tests/unit/middleware/test_prometheus_metrics.py
pytest -q
```

## Releases, persistence, and recovery

Startup uses `metadata.create_all()`, which does not upgrade existing schemas. Follow [the migration boundary](architecture.md#persistence-and-migrations) before changing deployed tables. Verify MySQL separately when it is the deployment target; current tests use SQLite.

Retain the tested commit and image digest, inject production configuration, and verify readiness plus a disposable API workflow in the target environment. Configure durable storage, backups, retention, and restore for the selected database. No automated promotion, migration, backup/restore, or rollback workflow is supplied.

During incidents inspect structured logs/request IDs, check `/health` separately from `/ready`, and investigate dependency reachability when readiness fails. Restrict diagnostics to the intended audience. Roll back to a retained image only after checking schema compatibility; restore data using the database operator's tested recovery procedure. Neither image rollback nor an available backup establishes recoverability on its own.
