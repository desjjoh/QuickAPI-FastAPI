# Deployment and operations

[Documentation index](../README.md#documentation)

[Graceful shutdown](shutdown.md) defines request admission, draining, deadlines,
entrypoint ownership, and process verification.

[Database readiness and recovery](database-lifecycle.md) documents probe deadlines,
shared checks, startup cleanup, and runtime recovery behavior.

## Database capacity and transport

[Database settings](database-settings.md) defines per-engine connection and waiting limits, acquisition/connect deadlines, verified TLS, and safe capacity failures. Configure trusted CA paths in the container filesystem and budget each worker/replica independently. Deployment certificate rotation and fleet capacity still require hosting-specific qualification.

## Runtime configuration and access

Use Python 3.12 and inject required settings from [Development](development.md#configuration). The image installs runtime-only [requirements.txt](../requirements.txt), checks dependency consistency, and copies application code; `.env` is excluded. Development tools are installed separately from `requirements-dev.txt` for local/CI checks. Use `ENV=production` to disable reload and align listening/published ports and probes.

Domain routes and any enabled operational endpoints have no application authentication. Documentation, diagnostics, and metrics default off in production; see [exposure controls](operational-exposure.md). Apply the consuming service's network/authentication boundary. CORS uses configured exact origins and is not an authentication boundary. The rate limiter is process-local; workers/replicas do not share state.

## Production container validation

The runtime uses the digest-pinned Python 3.12 Trixie base declared in the
Dockerfile. Builder and runtime share that base. Only the builder installs
`build-essential`; runtime requirements live in `/opt/venv`. The API and migration
command run as UID/GID `10001:10001`, with root-owned application code and
dependencies. Application logging uses standard output and needs no writable
application directory. Curl remains installed for Compose readiness probes.

### Updating the Python base

1. Select a supported Python 3.12 patch tag with the same Debian variant. Inspect
   its official registry manifest with
   `docker buildx imagetools inspect python:<patch>-slim-trixie`.
2. Update the Dockerfile's `PYTHON_IMAGE` tag and index digest together. Retain the
   digest in source control; changing a moving tag alone does not update the base.
3. Submit the update through CI. Require a fresh image build and the runtime
   identity, permissions, dependency, migration, HTTP/MySQL and shutdown checks.
   Review security scan results when that gate is enabled.

The base digest fixes the base artifact, not packages downloaded later by apt or
pip. Dependency requirements remain manually pinned; this does not promise
byte-for-byte reproducible builds. Do not override `PYTHON_IMAGE` in a release
build without reviewing and recording the selected source change.

### Qualifying the image

Build and qualify the runtime artifact against independent disposable MySQL:

```powershell
docker build -t quickapi-fastapi:local .
python -m scripts.test_image --image quickapi-fastapi:local
```

The command loads guarded `.env.test` credentials and creates the
`quickapi-fastapi-smoke` Compose project. It publishes no host ports and mounts no
development data. It waits for MySQL, applies migrations using the built image,
starts that image with production defaults, and checks CRUD, readiness/liveness,
favicon delivery, and disabled documentation/diagnostics/metrics. It also runs
non-root identity, code/dependency permissions, development/build-tool exclusion
and `pip check` checks, sends Docker's stop signal, and verifies exit zero and the final clean
shutdown record. Bounded logs are retained in `test-artifacts/production-mysql.log`;
the temporary project and storage are removed on completion or failure.

The check also creates a keyed item and updates it before stopping the API. It
replaces only the API container, verifies a new container identity with the same
image ID and unchanged MySQL container, and waits for readiness. The replacement
must return the retained item fields/version, replay the original create status
and exact response bytes without changing the item or collection, and accept a
fresh update and deletion. Both API instances must stop cleanly; logs from the
first instance are preserved before replacement.

This validates the selected local image and MySQL behavior. A local tag is not an
immutable release reference. Persistence is qualified across API container
replacement while the disposable MySQL container stays running. Its temporary
storage does not qualify database restarts or durable database volumes. Deployment storage, representative
future migrations, restore, failover, and release promotion have separate acceptance
criteria. The test database is disposable and is not a deployment configuration.

## Local Compose topology

The checked-in [Compose file](../docker-compose.yaml) is a local development stack, not a hosted production deployment definition. Its default project is `quickapi-fastapi-dev`. It includes MySQL 8.4.6, a project-scoped persistent volume, an authenticated database health check, API startup ordering, and a health check on the API's fixed internal port 8000. Both API/database host ports are loopback-only and configurable. No fixed container names are shared with sibling apps.

Compose reads `.env` and overrides container-specific settings: `HOST=0.0.0.0`, `PORT=8000`, `ENV=production`, and a local MySQL service URL. Native Python keeps its own port/mode/database URL. The unused `DEBUG`/`WORKERS` entries were removed. See [local setup, credentials, persistence, and reset commands](development.md#local-compose).

Development, persistence tests, and built-image qualification all use MySQL.
The runtime-image check uses its own temporary project and explicit migrations;
it does not mutate the development or regular test database. See [Testing](testing.md)
for verification boundaries and [Verification](verification.md) for dated evidence.

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
  "version": "1.3.0",
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

Apply `python -m alembic upgrade head` before starting the API; startup checks revision compatibility without changing the schema. See [Migrations](migrations.md) for native/container commands. Automated persistence and built-image checks use disposable MySQL; verify the actual deployment separately.

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
