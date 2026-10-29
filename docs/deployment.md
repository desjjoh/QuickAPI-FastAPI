# Deployment and operations

[Documentation index](../README.md#documentation)

## Runtime configuration and access

Use Python 3.12 and inject required settings from [Development](development.md#configuration). The image installs runtime-only [requirements.txt](../requirements.txt), checks dependency consistency, and copies application code; `.env` is excluded. Development tools are installed separately from `requirements-dev.txt` for local/CI checks. Use `ENV=production` to disable reload and align listening/published ports and probes.

Domain routes and any enabled operational endpoints have no application authentication. Documentation, diagnostics, and metrics default off in production; see [exposure controls](operational-exposure.md). Apply the consuming service's network/authentication boundary. CORS uses configured exact origins and is not an authentication boundary. The rate limiter is process-local; workers/replicas do not share state.

## Production container validation

Build a local image using the same configuration pattern as CI. A local tag is not an immutable release reference:

```bash
docker build -t quickapi-fastapi:local .
docker volume create quickapi-fastapi-smoke
docker run --rm --mount source=quickapi-fastapi-smoke,target=/data \
  -e APP_NAME=QuickAPI -e APP_VERSION=1.0.0 -e ENV=production -e PORT=8000 \
  -e DATABASE_URL=sqlite+aiosqlite:////data/quickapi.db \
  quickapi-fastapi:local python -m alembic upgrade head
docker run --rm -p 8000:8000 \
  --mount source=quickapi-fastapi-smoke,target=/data \
  -e APP_NAME=QuickAPI -e APP_VERSION=1.0.0 \
  -e ENV=production -e LOG_LEVEL=INFO \
  -e HOST=0.0.0.0 -e PORT=8000 \
  -e DATABASE_URL=sqlite+aiosqlite:////data/quickapi.db \
  quickapi-fastapi:local
curl --fail http://localhost:8000/ready
curl --fail http://localhost:8000/api/v1/items/
```

SQLite makes the smoke test self-contained; `/data/quickapi.db` uses the disposable smoke volume shared by migration and API containers. Deploy with the async database URL and durable storage required by your service. CI checks startup and an API read against the built image; it does not validate a production deployment or MySQL compatibility.

After stopping the container, remove the smoke volume with `docker volume rm quickapi-fastapi-smoke` when its data is no longer needed.

Run the container in one terminal and curl checks in a second. The example uses Bash continuation; use a single line or PowerShell continuation syntax in PowerShell.

## Local Compose topology

The checked-in [Compose file](../docker-compose.yaml) is a local development stack, not a hosted production deployment definition. Its default project is `quickapi-fastapi-dev`. It includes MySQL 8.4.6, a project-scoped persistent volume, an authenticated database health check, API startup ordering, and a health check on the API's fixed internal port 8000. Both API/database host ports are loopback-only and configurable. No fixed container names are shared with sibling apps.

Compose reads `.env` and overrides container-specific settings: `HOST=0.0.0.0`, `PORT=8000`, `ENV=production`, and a local MySQL service URL. Native Python keeps its own port/mode/database URL. The unused `DEBUG`/`WORKERS` entries were removed. See [local setup, credentials, persistence, and reset commands](development.md#local-compose).

Compose provides a local MySQL development topology. The CI runtime-image smoke
uses SQLite and explicitly applies the baseline before API startup. Separate disposable MySQL jobs exercise repository/API persistence; the image smoke does not
qualify MySQL failure paths or representative future data upgrades. See [Testing](testing.md) for verification boundaries and
[Verification](verification.md) for dated execution evidence.

## Application lifespan and operational endpoints

FastAPI's lifespan starts registered services before the app becomes ready. The
database service checks its Alembic revision, readiness requires startup completion
and healthy registered services, and shutdown stops only successfully started
services in reverse order. Partial startup failure rolls back already-started
services. The unversioned operational surface is shown below. `/info` and `/system` require
`DIAGNOSTICS_ENABLED`; `/metrics` requires `METRICS_ENABLED`. Both flags default off
in production, and enabling them supplies no authentication.

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
means the running process should temporarily receive no application traffic. Readiness still performs bounded dependency checks internally, but its public
response omits dependency names/timings in every environment. `/system` retains its
existing `db` summary when diagnostics are enabled. See the
[public probe contract](operational-exposure.md#public-probes-and-readiness).

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
  "timestamp": "2026-09-01T12:00:00Z"
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
http_requests_total{method="GET",route="/api/v1/items/",status="200"} 42
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

Enabled operational endpoints have no application authentication.
Their payloads contain operational metadata but no credentials, connection strings,
environment-variable values, or other secrets. Apply a network trust boundary or
authentication before exposing them where host/process metadata is considered
sensitive.

Prometheus traffic metrics exclude `/health`, `/ready`, `/info`, `/system`, and
`/metrics`. Other routes use bounded declared route templates and normalized methods;
unknown routes use `<unmatched>`. See [Metrics and request outcomes](#metrics-and-request-outcomes)
for the complete labels, units, and completion/abort contract.

Run the targeted operational contract checks and then the complete suite with the
established commands:

```bash
pytest -q --no-cov tests/integration/errors/test_open_api.py
pytest -q --no-cov tests/unit/middleware/test_prometheus_metrics.py
pytest -q
```

## Releases, persistence, and recovery

Apply `python -m alembic upgrade head` before starting the API; startup checks revision compatibility without changing the schema. See [Migrations](migrations.md) for native/container commands. Verify MySQL separately when it is the deployment target; automated persistence suites cover SQLite and disposable MySQL.

Retain the tested commit and image digest, inject production configuration, and verify readiness plus a disposable API workflow in the target environment. Configure durable storage, backups, retention, and restore for the selected database. Compose supplies a one-shot local migration step. No hosted promotion, backup/restore, or application rollback workflow is supplied.

During incidents inspect structured logs/request IDs, check `/health` separately from `/ready`, and investigate dependency reachability when readiness fails. Restrict diagnostics to the intended audience. Roll back to a retained image only after checking schema compatibility; restore data using the database operator's tested recovery procedure. Neither image rollback nor an available backup establishes recoverability on its own.

## Metrics and request outcomes

The schema matches QuickAPI-Express and QuickAPI-NestJS, with Express's separate
abort counter:

| Metric                        | Labels                      | Meaning                                                                                                 |
| ----------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------- |
| `http_requests_total`         | `method`, `route`, `status` | Completed responses, including emitted 4xx/5xx and pre-header timeout 408                               |
| `http_request_duration_ms`    | `method`, `route`, `status` | Completed-response duration in milliseconds; buckets 5, 15, 50, 100, 250, 500, 1000, and +Inf           |
| `http_requests_aborted_total` | `method`, `route`           | Incomplete responses: disconnect, stream timeout, cancellation, or failure without a completed response |

`route` is the full declared template, for example `/api/v1/items/{id}`, including
declared mount prefixes. Missing routes and rejections before routing use
`<unmatched>`; unsupported methods use `<other>`. Labels never contain raw item IDs,
unknown URLs, queries, client addresses, or request IDs. The five root operational
paths `/health`, `/ready`, `/info`, `/system`, and `/metrics` remain excluded from
all three traffic metrics. Their access logs are still emitted.

One shared per-request observation feeds access logs and metrics exactly once.
Completion is the final response body accepted by ASGI send, not return from the
handler, dependency cleanup, or background work. An observed disconnect/send failure,
external cancellation, or owned streaming deadline ends an incomplete response.
A started 200 that is truncated is an abort, never a completed 200 or a fabricated
499/0 response. The observation retains a status only when headers were accepted;
aborts have no status metric label. Late cleanup, failures, or attempted output do
not change the recorded outcome. The observer adds no receive-reader task; it uses
the timeout middleware's existing disconnect observation and ASGI channel wrappers.
These are server-side transport observations, not proof the peer consumed every byte.

Dashboard queries use the `route` label and millisecond duration thresholds.
Histogram grouping/filtering includes `status`; `_bucket`, `_sum`, and `_count`
series derive from `http_request_duration_ms`. Completed-response histograms exclude
aborted requests, which are measured by `http_requests_aborted_total`.

## HTTP policy configuration

See [HTTP configuration](http-policy.md) for settings, defaults, validation, proxy
chain behavior, and server receive limits. Optional `.env.example` overrides are
commented; process environment wins over `.env` and omitted values use code defaults.
Set actual browser origins and explicit proxy IPs/CIDRs for the hosting topology.
The application owns forwarding resolution; external Uvicorn commands must use
`--no-proxy-headers`, as the normal entrypoint already does. Real ingress trust,
direct-port denial, and slow-header/whole-upload protection still require deployed
verification; application deadlines do not establish those transport guarantees.

## Limiter capacity and probe policy

[Rate limiting](rate-limiting.md) uses an exact bounded rolling window per application
process. Defaults are 200 requests/60 seconds/client, 10000 clients, and a combined
maximum of 2000000 timestamp slots. Quota exhaustion returns 429; a new identity at
store capacity receives 503; both carry `Retry-After`. Existing clients are not evicted
or reset to admit new identities. Probes, diagnostics, metrics, and preflights share
the resolved client's quota. Configure proxy trust, probe frequency, and capacity for
the selected topology. Limiter failures precede CORS; see the documented browser
response boundary. Multi-worker/replica enforcement is independent; distributed
quotas and hosting-level behavior require separate qualification.

## Production logging

[Logging and diagnostics](logging.md) defines UTC JSON records, safe error metadata,
and the dependency logging bridge. INFO shows lifecycle events and suppresses successful
request access records; choose DEBUG when those records are required. Request bodies,
queries, credentials, SQL parameters, raw paths, and exception text are not logging
payloads. Log access/retention/shipping require deployment-level configuration.
