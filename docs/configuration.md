# Configuration

[Documentation index](../README.md#documentation)

## Defaults and overrides

[Settings](../app/config/environment.py) owns defaults and startup validation.
Normal precedence is **process environment > `.env` > code defaults**. Settings are
loaded once at startup; restart after changing configuration. Constructor values
used by tests take precedence over those sources.

[`.env.example`](../.env.example) groups required identity/database values and optional
policy overrides. Commented assignments show actual defaults, not additional required
configuration. Copy it only when creating a new `.env`; reconcile an existing file
without discarding credentials or local overrides. Keep shared comments synchronized.
Lists use comma-separated values, not JSON; surrounding entry whitespace is trimmed
and duplicates are removed. Header names/media types normalize to lowercase; methods
must already be uppercase. Booleans accept exactly `true` or `false`.

Missing optional values use defaults. Empty values are rejected except `TRUST_PROXY`,
`CORS_ALLOWED_HEADERS`, and `CORS_EXPOSED_HEADERS`, where empty means an empty list.
The existing published-port settings separately accept empty values as defaults.

## Application and environment targets

| Variable               | Requirement                                                                  |
| ---------------------- | ---------------------------------------------------------------------------- |
| `APP_NAME`             | Non-empty, at most 120 characters.                                           |
| `APP_VERSION`          | Three-part semantic version such as `1.3.0`.                                 |
| `ENV`                  | `development`, `test`, or `production`.                                      |
| `LOG_LEVEL`            | `DEBUG`, `INFO`, `WARN`, or `ERROR`; default INFO hides successful requests. |
| `HOST`                 | Bind address; defaults to `0.0.0.0`.                                         |
| `PORT`                 | Integer from 1 through 65535.                                                |
| `API_PUBLISHED_PORT`   | Optional host API port, 1-65535; missing/empty defaults to 8000.             |
| `MYSQL_PUBLISHED_PORT` | Optional host MySQL port, 1-65535; missing/empty defaults to 3310.           |
| `TIMEZONE`             | Valid IANA identifier; defaults to `Etc/UTC`.                                |
| `DATABASE_URL`         | SQLAlchemy async URL; MySQL uses `mysql+asyncmy://...`.                      |

Pydantic validates configuration while importing the application. Missing or invalid
required values produce a field-by-field diagnostic and a non-zero exit rather than
starting a partially configured server. `.env` is for local development; deployment
systems should inject secrets and configuration instead of baking them into images.

| Context                      | Target and configuration                                                                  |
| ---------------------------- | ----------------------------------------------------------------------------------------- |
| Native development           | `.env`; project `quickapi-fastapi-dev`; MySQL `127.0.0.1:3310`, persistent volume         |
| Containerized development    | Compose's internal `mysql:3306` URL and fixed API port 8000; API runs `ENV=production`    |
| Disposable persistence tests | `.env.test`; project `quickapi-fastapi-test`; MySQL `127.0.0.1:3311`, temporary storage   |
| Image/rollback qualification | Separate guarded disposable projects; no development data or published API/database ports |

`DATABASE_URL` must use `mysql+asyncmy`. Process environment overrides `.env`;
the test wrapper explicitly selects its test connection and does not fall back
to development. Review [Testing](testing.md#database-safety) before any destructive
fixture. Public URL/port settings are not credentials or access control.

`DEBUG`, `WORKERS`, and `METRICS_API_KEY` are not consumed application settings.
Setting a metrics key does not protect `/metrics`. Deployment systems inject
secrets rather than baking `.env` into images. `VERSION` and `.env.example`'s
`APP_VERSION` must match when preparing a release.

## Browser and HTTP settings

| Setting                | Default                                                       | Validation                                                                                                                       |
| ---------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `CORS_ORIGINS`         | `http://localhost:3000`                                       | 1-100 exact serialized HTTP(S) origins; no wildcard, credentials, path/trailing slash, query, fragment, or explicit default port |
| `CORS_METHODS`         | `GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS`                      | Non-empty subset of `HTTP_ALLOWED_METHODS`                                                                                       |
| `CORS_ALLOWED_HEADERS` | `content-type,authorization,x-requested-with,idempotency-key` | Up to 100 supported names; forwarding/hop-by-hop names are reserved                                                              |
| `CORS_EXPOSED_HEADERS` | `authorization,set-cookie`                                    | Same syntax/count rules; empty disables configured exposed headers                                                               |
| `CORS_CREDENTIALS`     | `true`                                                        | Boolean                                                                                                                          |
| `CORS_MAX_AGE_SECONDS` | `86400`                                                       | Integer 0-86400; zero disables preflight caching                                                                                 |

### Request budgets and application policy

| Setting                         | Default         | Accepted integer range |
| ------------------------------- | --------------- | ---------------------- |
| `REQUEST_TIMEOUT_MS`            | 10000           | 1-2147483647           |
| `REQUEST_FIRST_BODY_TIMEOUT_MS` | 5000            | 1-2147483647           |
| `REQUEST_CHUNK_TIMEOUT_MS`      | 2000            | 1-2147483647           |
| `HTTP_MAX_BODY_BYTES`           | 1048576 (1 MiB) | 1-1073741824           |
| `HTTP_MAX_HEADER_COUNT`         | 100             | 1-10000                |
| `HTTP_MAX_SINGLE_HEADER_BYTES`  | 4096            | 1-1048576              |
| `HTTP_MAX_TOTAL_HEADER_BYTES`   | 8192            | 1-16777216             |

Both body-wait deadlines must be no greater than the total response deadline.
The single-header byte budget must not exceed the total budget. Fractions, booleans,
blank values, non-finite values, and out-of-range numbers fail startup. Milliseconds
convert to seconds only when configuring the existing Python timeout middleware;
[response/stream/cancellation behavior](deployment.md#transport-deadlines) is unchanged.

Header byte accounting remains name + value, excluding wire framing. Parsed-header
budgets run before CORS preflight short-circuiting and after sanitizer filtering,
matching application accounting for retained headers. Trusted proxy handling
consumes headers only after the original count/size budgets pass. This protects the
application policy boundary; a server may reject a request before ASGI with its own
limits, and these settings do not cap memory used while parsing wire headers.

`HTTP_ALLOWED_METHODS` defaults to `GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS` and accepts
only a non-empty subset of these methods. `HTTP_ALLOWED_CONTENT_TYPES` defaults to
`application/json,multipart/form-data`; it accepts 1-100 exact media types without
parameters or wildcards. Existing route validation and body-method rules remain:
allowing a media type does not change an item's JSON schema or make no-body methods
accept bodies. Chunked transfer and unsafe-header restrictions remain code policy.
[Rate limiting](security.md#rate-limiting) defines the three validated rolling-window settings,
combined storage bound, response timing, and probe/preflight policy.

### Trusted proxies

`TRUST_PROXY` defaults to empty. It accepts at most 100 explicit IPv4/IPv6
addresses or CIDRs, not hostnames, hop counts, scoped IPv6, wildcards, or blanket
`/0` networks. The application owns forwarding interpretation; external Uvicorn
commands must disable Uvicorn's separate proxy handling with `--no-proxy-headers`.
See [Security](security.md#proxy-and-browser-boundaries) for the ingress contract.

## Database capacity and TLS

`DATABASE_URL` must select MySQL through `mysql+asyncmy`; other drivers are rejected. Optional settings have code defaults and process
environment overrides `.env`. Explicit tests select their own configuration.

| Setting                      | Default | Accepted values                                       |
| ---------------------------- | ------- | ----------------------------------------------------- |
| `DB_POOL_CONNECTION_LIMIT`   | `10`    | Integer 1–1000                                        |
| `DB_POOL_QUEUE_LIMIT`        | `50`    | Integer 0–10000                                       |
| `DB_POOL_ACQUIRE_TIMEOUT_MS` | `1000`  | Integer 1–2147483647                                  |
| `DB_CONNECT_TIMEOUT_MS`      | `10000` | Integer 1–2147483647                                  |
| `DB_SSL`                     | `false` | Literal `true` or `false`                             |
| `DB_SSL_CA_FILE`             | Omitted | Nonempty readable PEM CA path; requires `DB_SSL=true` |

Blank, fractional, negative, boolean-as-number, and malformed values fail validation.
TLS requires MySQL. Invalid CA files fail configuration rather than weakening
verification. Relative CA paths resolve from the command's working directory.
MySQL URL query options are limited to `charset`; connection/TLS policy cannot be
overridden through driver query options. Restart after configuration changes.

Application startup, readiness queries, Alembic commands, and disposable MySQL
fixtures use the shared engine factory. Migration helpers using an existing
connection inherit that connection's policy. Pool lifecycle and migration checks
use actual MySQL sessions, including the late-connection disposal tests.

### TLS verification

Local development/test MySQL can remain plaintext with `DB_SSL=false`. To enable
verified transport:

```dotenv
DB_SSL=true
DB_SSL_CA_FILE=/path/to/trusted-mysql-ca.pem
```

Omit the CA path to use system trust. The client requires a valid certificate chain,
matching DNS hostname or IP subject alternative name, and TLS 1.2 or newer. Unlike
the sibling Node driver policy, Python can verify an IP SAN; it does not bypass
identity verification for IP addresses. The connection is checked for an active
TLS cipher before admission to SQLAlchemy. There is no insecure verification switch
or fallback to plaintext when TLS is enabled.

#### Windows entrypoints

The pinned asyncmy TLS socket upgrade fails with Windows' default Proactor loop.
When TLS is enabled, `python -m app.main` and built-in migration commands select a
selector loop. Non-TLS behavior retains the platform's normal loop selection.
Custom Windows asyncio callers must use the compatible loop, for example:

```python
from app.config.event_loop import run_database

run_database(your_database_coroutine())
```

For an external Uvicorn command use the application's loop constructor as well as
its proxy policy:

```powershell
python -m uvicorn app.config.application:app --loop app.config.event_loop:server_loop_factory --no-proxy-headers
```

The selector loop has platform limitations; large-scale capacity is not established
by local Windows verification. Linux keeps normal Uvicorn loop selection.

## Readiness and shutdown budgets

These optional settings use code defaults; process environment overrides `.env`.

| Setting                         | Default | Accepted values                             |
| ------------------------------- | ------- | ------------------------------------------- |
| `DB_READINESS_TIMEOUT_MS`       | `1000`  | Integer 1–2147483647                        |
| `DB_READINESS_CACHE_MS`         | `1000`  | Integer 0–2147483647; zero disables caching |
| `DB_MIGRATION_CHECK_TIMEOUT_MS` | `5000`  | Integer 1–2147483647                        |

Empty, fractional, negative, and malformed values fail startup validation. The
settings apply to the supported MySQL transport. [Transport settings](configuration.md#database-capacity-and-tls)
separately bound MySQL acquisition and connection establishment.

| Setting                 | Default | Validation                                           |
| ----------------------- | ------- | ---------------------------------------------------- |
| `HTTP_DRAIN_TIMEOUT_MS` | `25000` | Integer 1–2147483647                                 |
| `SHUTDOWN_TIMEOUT_MS`   | `30000` | Integer 1–2147483647; greater than HTTP drain budget |

Process environment overrides `.env`; omitted settings use code defaults. Blank,
fractional, boolean, negative, and out-of-range values are invalid. The overall
budget begins when shutdown starts, rather than restarting at each cleanup step.

Local Compose gives the API 35 seconds to stop, allowing the default 30-second
application budget to finish. If changing the application budget, configure Docker
or the hosting supervisor's termination grace to exceed it. A shorter external
grace period can kill the process before application cleanup finishes.

## Operational surfaces

Documentation, diagnostics, and metrics are independently enabled by optional
booleans. Omitted values default to `true` in
`development`/`test` and `false` in `production`.

| Setting               | Controlled route families                                                                           |
| --------------------- | --------------------------------------------------------------------------------------------------- |
| `DOCS_ENABLED`        | `/docs`, `/redoc`, `/openapi.json`, including Swagger OAuth redirect and nested documentation paths |
| `DIAGNOSTICS_ENABLED` | `/info`, `/system`                                                                                  |
| `METRICS_ENABLED`     | `/metrics`                                                                                          |

Only literal `true`/`false` env values are accepted. Blank, numeric, mixed-case, and
other ambiguous values fail startup. Each flag independently overrides the environment
default. Precedence remains process environment > `.env` > code defaults; restart to
apply changes. The comments in `.env.example` show **production** defaults, so leaving
those assignments commented enables the endpoints when running in development/test.
For example, a private production scraper can explicitly enable only metrics:

```dotenv
METRICS_ENABLED=true
```

Native Python with the example's `ENV=development` enables all three by default.
Compose deliberately overrides `ENV=production`, so its API disables all three unless
explicit overrides are supplied. Local `DOCS_ENABLED=true` can enable container docs;
do not mistake that local override for a production access policy.

## Rate-limit settings

The limiter enforces a bounded exact rolling window. Optional
overrides in `.env.example` show code defaults; normal precedence remains process
environment > `.env` > defaults. Restart to apply changes.

| Setting                  | Default | Accepted integer range |
| ------------------------ | ------- | ---------------------- |
| `RATE_LIMIT_WINDOW_MS`   | 60000   | 1-86400000             |
| `RATE_LIMIT_MAX`         | 200     | 1-10000                |
| `RATE_LIMIT_MAX_CLIENTS` | 10000   | 1-100000               |

`RATE_LIMIT_MAX * RATE_LIMIT_MAX_CLIENTS` must not exceed **2000000 timestamp slots**.
Missing values use defaults; blank/fractional/non-finite/boolean/out-of-range values
fail startup. The same shared policy validates direct limiter construction. Raising
the request quota may require lowering client capacity to retain the combined bound.
For example, 1000 requests with 2000 tracked clients reaches the same slot ceiling.

The default quota is **200 admitted requests in the preceding 60 seconds per client**.
There is no separate burst budget or fixed-window reset. Python callers use
`admit(identity)` to obtain an explicit admission/rejection decision. HTTP errors use
the `{status,message,timestamp}` envelope.

## Replay settings

| Setting                           | Default | Bounds                       |
| --------------------------------- | ------- | ---------------------------- |
| `IDEMPOTENCY_MAX_RESPONSE_BYTES`  | 65536   | Integer UTF-8 bytes, 1–65536 |
| `IDEMPOTENCY_CLEANUP_BATCH_SIZE`  | 100     | Integer rows, 1–1000         |
| `IDEMPOTENCY_CLEANUP_MAX_BATCHES` | 10      | Integer batches, 1–100       |

Batch size multiplied by batch count must not exceed 10000 rows per sweep.
Retention is fixed at 24 hours; cleanup runs hourly. These bounds do not impose
an absolute table-size cap at arbitrary throughput. See
[Architecture](architecture.md#request-idempotency) for replay/cleanup ownership.
