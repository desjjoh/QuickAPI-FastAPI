# Architecture

[Documentation index](../README.md#documentation)

## Architecture

```text
app/
├── api/
│   ├── api_routes.py                 # top-level route composition
│   ├── system/                       # probes, diagnostics, metrics, metadata
│   └── v1/items/                     # item controllers, services and Pydantic models
├── common/
│   ├── docs/                         # OpenAPI contract customization
│   ├── handlers/                     # exception and lifecycle behavior
│   ├── middleware/                   # transport/security/observability policies
│   ├── models/                       # shared errors, parameters, pagination
│   ├── services/                     # shared idempotency execution and cleanup
│   └── store/                        # request context and rate-limit state
├── config/                           # app assembly, settings, DB, logging, metrics
├── database/
│   ├── entities/                     # SQLAlchemy mappings
│   └── repositories/                 # queries and caller-owned persistence
├── public/                           # static assets
└── main.py                           # executable entry point
tests/
├── unit/                             # isolated behavior
├── integration/                      # real session/repository and app composition
└── e2e/                              # complete HTTP and lifespan behavior
```

Controllers declare HTTP routes, delegate application work and validate the result
into Pydantic response models. Services own application logic and return operation
results; repositories perform SQL using
the caller's session. Application assembly is centralized in
`app/config/application.py`. [Services](architecture.md#controller-and-service-boundaries) describes the shared item and
system boundary and session ownership.

## Flexible route spelling

Item and system controllers use [FlexibleRouter](../app/common/handlers/flexible_router.py)
to accept named HTTP endpoints with or without a trailing slash, without redirects,
and match static path text without case sensitivity. Captured parameter values retain
their original spelling, including case-sensitive resource IDs.
Controllers declare each operation once. The router registers the canonical path
first and hides the alternate spelling from OpenAPI. URL generation selects the
canonical route. Nested router inclusion copies existing routes without generating
another pair; response models, status codes, dependencies and route classes survive.

Use `""` for a collection root mounted beneath a prefix, such as `/api/v1/items`.
An explicit `"/"` remains a single root route, as used by the system greeting.
Named paths such as `/health` and `/items/{id}` receive both spellings. Item routes
retain `ApplicationRoute` and their transaction markers. Operational exposure
settings protect all spellings. Framework-provided documentation routes use the same
case and slash matching. Logs and metrics retain canonical route labels.

GET routes accept HEAD automatically without adding an OpenAPI operation. Explicit
HEAD handlers take precedence over that fallback. HEAD executes the selected handler
and response preparation, preserving status and representation headers; the outer
HTTP response wrapper suppresses body bytes, including error responses.

## Request lifecycle and middleware order

Starlette wraps middleware in reverse registration order. Consequently, the last
middleware added in `create_app()` is the first to see a request. The effective
inbound order is:

```text
request outcome → server error fallback → admission → cleanup → trusted proxy
→ request context → request logging → metrics → security headers → rate limit
→ header sanitization → header limits → timeout → content type → method allowlist
→ CORS → body limit → application error boundary → operational exposure → routing/controller
```

Responses unwind through the same layers in reverse. This is intentional:

1. One request-outcome observer wraps Starlette's server error handler so final
   500 responses and transport failures are observed. Cleanup clears request context
   even after failures.
2. Explicit IP/CIDR proxy trust resolves client identity before request context.
   Request identity is established before logging and returned as `X-Request-ID`.
3. Header sanitization and parsed-header budgets run before preflight responses;
   unknown allowed-to-drop headers are removed before application size accounting.
   Trusted-proxy interpretation retains its early raw-header bounds.
4. Logging and metrics subscribe to the same outcome before policy checks.
   Duration ends when the final body is accepted by ASGI send, or when an abort
   is observed; downstream cleanup cannot extend it. A completed 408/500 counts as
   a response; a truncated stream counts only as an abort.
5. FastAPI validates declared inputs. Controllers delegate to services, which borrow
   the request session and apply operation rules. Controllers assign the awaited
   result to a named variable, then validate the declared response model. FastAPI
   prepares and serializes the HTTP response.

Middleware rejections use the same error renderer as routed HTTP exceptions, so
clients do not need separate parsing behavior for transport and application errors.
The [bounded rolling-window limiter](security.md#rate-limiting) is process-local, with
fixed-capacity timestamp rings and expiry-ordered client storage. Admission occurs
before CORS preflights and later policy rejections. Application failures are rendered
inside the header wrappers; failures after headers start propagate without another
response. Shared storage is required for a global quota across workers/replicas.

[Metrics and request outcomes](deployment.md#metrics-and-request-outcomes) defines
labels, exclusions, units, and the dashboard migration. Declared route templates
include mount prefixes; concrete IDs, query values, and unknown paths never become
access-log routes or metric labels. [Logging](deployment.md#logging) uses DEBUG for successful requests, WARNING for client errors
and aborts, and ERROR for server failures. Console access records use `ABORTED` for
incomplete responses; production records expose the structured outcome.

[HTTP configuration](configuration.md#browser-and-http-settings) defines defaults, environment overrides,
validation, proxy ownership, and the separate server receive-protection boundary.

[Operational exposure](security.md#operational-access) controls per-app route registration
and reserves disabled path families. Native docs are installed only when enabled.
Public readiness serializes no dependency details; internal service checking remains.

## Persistence and migrations

[Database readiness and recovery](architecture.md#database-lifecycle) uses one shared,
on-demand task per application database service, with monotonic result caching.
Probe cancellation retires only its connection; caller cancellation is isolated
from shared work. Startup revision verification has its own deadline and failure
cleanup. Runtime outages leave the engine available for replacement connections.

[Mutation transaction ownership](architecture.md#mutation-transactions) uses `ApplicationRoute` and
`@transactional` on the four item mutation endpoints. One fresh session/transaction
covers dependency resolution, service work, repository writes, and FastAPI
response validation/JSON rendering before commit. `get_session(request)` borrows
that owner for marked routes and creates/closes a read session for other routes.
Repositories require an active transaction and do not commit or roll back.
Item controllers delegate to `ItemService`; service work and model validation run
inside that same transaction boundary.

[Alembic migrations](setup.md#database-migrations) own schema creation and changes. The API checks
that the connected database revision matches the single source head before startup
completes; it does not apply migrations or call `metadata.create_all()`. Apply
`python -m alembic upgrade head` explicitly before starting native Python. Compose
uses a one-shot migration service before API startup. Revision equality does not
establish that manually edited tables match the models; schema comparison and
data/rollback compatibility need separate evidence.

## Controller and service boundaries

### Shared boundary

Item and system controllers declare routes, request parameters, response models,
status codes and OpenAPI metadata. They delegate application work to services.
Services own repository queries, missing-resource decisions and probe calculations.
Controllers receive those results and construct validated Pydantic response models,
including the pagination envelope. Each asynchronous call assigns its result to a
named local variable before response conversion; controllers do not use
`return await service.operation(...)`.

HTTP response handling stays in controllers: readiness maps the validated `ready`
value to status 200 or 503, favicon uses a file response, and metrics uses the
Prometheus media type. File paths and metrics bytes come from the system service.
FastAPI retains its normal input validation, response validation and serialization.

Idempotency is declared on transactional routes, after normal request validation.
The shared execution layer handles claims, replay and atomic response storage; domain
services remain responsible for their operation rules. See [Durable mutation retries](architecture.md#request-idempotency).

### Item operations

`ItemService` owns create, list, fetch, PATCH, PUT and delete behavior. It converts
validated request models to repository inputs and returns ORM entities or an
items/count pair. Controllers convert entities to `ItemResponse` and construct
`PaginatedResult[ItemResponse]`. Missing-resource errors retain the existing status
and message. PATCH uses only supplied fields; PUT supplies the complete model.

`get_item_service` creates a request-scoped service through FastAPI dependencies.
Its `AsyncSession` comes from `get_session`. Marked mutation routes borrow the
existing route-owned transaction session; ordinary reads use the normal read
session. Services and repositories never independently commit or roll back an
HTTP mutation. A new request gets a new service/session; no mutable session is
stored on an application-wide item singleton.

Item prices remain `Decimal` through request validation, services and repositories.
Controllers validate the returned ORM values, and response models serialize prices
as JSON numbers with `createdAt`/`updatedAt` timestamp aliases. No service-side
float conversion is needed.

```python
@router.post("/", response_model=ItemResponse, status_code=201)
@transactional
async def create(
    payload: ItemBase,
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    item = await service.create(payload)
    return ItemResponse.model_validate(item)
```

Service execution and controller response validation happen before the transaction
owner checks activity and commits. Validation failures roll back writes. The
[transaction contract](architecture.md#mutation-transactions) also covers timeout, disconnect, cleanup
and uncertain commit outcomes. Non-HTTP callers must supply a session and explicitly
own any mutation transaction themselves.

### System operations

Application assembly supplies `SystemService`, `SystemInfoService` and
`SystemDiagnosticsService` per application. Typed dependency functions provide
them to controllers. They use the application's lifecycle and startup timestamps.
These objects do not own separate startup/shutdown resources.

`SystemService` calculates the root greeting, liveness and readiness results. Liveness
does not query dependencies. Readiness requires completed startup and healthy
registered dependencies and exposes no dependency details. `SystemInfoService`
collects runtime identity, and `SystemDiagnosticsService` collects bounded diagnostics.
Collected health, identity and nested diagnostics use plain `TypedDict` structures,
which provide static type checking without runtime response validation. Controllers
construct the public probe models and validate identity/diagnostics with their
Pydantic response models; all nested diagnostics are validated there as well.
Operational exposure middleware continues to prevent disabled endpoints from
invoking those services or the metrics exporter.

## Mutation transactions

### Route contract

Mutation endpoints opt into a shared transaction boundary with `@transactional`.
Their router uses `ApplicationRoute`; the decorator marks the endpoint without
replacing its signature or implementing a middleware transaction around every
request. Controllers delegate item operations to a request-scoped `ItemService`,
which borrows the owned session and returns the operation result. Controllers
validate that result into the declared response model before returning it.

```python
router = APIRouter(route_class=ApplicationRoute)


@router.post("/", response_model=ItemResponse, status_code=201)
@transactional
async def create(
    payload: ItemBase,
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    item = await service.create(payload)
    return ItemResponse.model_validate(item)
```

The item create, PATCH, PUT, and POST deletion endpoints use this boundary. Unmarked
routes retain their normal FastAPI handler and dependency behavior. GET requests
are not wrapped in a mutation transaction; SQLAlchemy can still use a read
transaction for their queries.

### Execution order

1. Allocate a fresh request-owned `AsyncSession` with automatic transaction start
   disabled and begin one explicit transaction before resolving dependencies or
   calling the controller.
2. `get_session(request)` yields that same session. Repeated dependency resolution
   shares the owner rather than allocating another connection or transaction.
3. Run the service's lookup, missing-resource checks, writes, flushes and refreshes,
   followed by controller response-model conversion, inside the transaction.
4. Let FastAPI's normal handler perform response-model validation, serialization,
   alias/exclusion handling, status/header preparation, and JSON rendering.
5. Flush any remaining writes and check request activity immediately before
   entering commit. Commit only after a buffered JSON response has been prepared. On successful
   commit, close the session and return that response to ASGI for delivery.

No response bytes are sent by the route owner before commit. Existing route
declarations remain the source for response models, status codes, and OpenAPI.
There is no copied serializer or second framework response pipeline. Item revision
checks and conditional writes participate in this same transaction; response
validation failures roll back both changed fields and the revision increment.

### Failure and cleanup

Exceptions during lookup, persistence, validation, serialization, rendering or
commit propagate through the transaction context. It attempts rollback and cleanup;
existing application exception handlers produce the client error response. A
prepared JSON response with status 400 or above is explicitly rolled back rather
than committed. An already-owned request or already-active factory session is
rejected instead of silently joining or opening a nested transaction.

Marked routes require buffered JSON and cannot attach background tasks. Streaming,
file, and deferred-background responses are rejected before commit. Unmarked routes
retain their existing response capabilities. These restrictions keep SQL work and
the mutation response inside one finite preparation boundary.

FastAPI request-scoped dependency teardown, outer middleware, and network delivery
can run after commit. The borrowed session must not be used for new work there.
Automatic transaction start remains disabled, so ordinary SQL on the completed
session fails rather than silently beginning another transaction. Future independent
background operations must own their own session/transaction.

### Repository callers

Repositories perform SQL, flushes, and refreshes. They require an active transaction
for mutations and never commit, roll back, or open a transaction independently.
Callers outside the HTTP route boundary must own the transaction explicitly:

```python
from decimal import Decimal

async with SessionLocal(autobegin=False) as db:
    async with db.begin():
        first = await repo.create(db, item_in={"name": "First", "price": Decimal("1.00")})
        await repo.update(db, first, {"description": "Saved together"}, first.version)
        await repo.create(db, item_in={"name": "Second", "price": Decimal("2.00")})
```

All operations above commit together on context exit. A repository return value is
not evidence that a mutation has committed. Failure handling belongs to the caller's
transaction boundary. Tests can inject the session factory to point transactional
routes at their guarded MySQL engine; a separate session dependency must not replace
the owner with an independently managed transaction.

### Expiry and commit outcomes

Timeout middleware and the route owner share a monotonic deadline and abandonment
state. The owner checks activity before allocating a session, after logical begin,
after actual connection acquisition/BEGIN, and after response preparation and final
flush, immediately before commit. The acquisition check runs through SQLAlchemy's
session `after_begin` event, before the first business statement. An expired pool
waiter cannot acquire a connection later and begin its mutation.

For a marked mutation, HTTP timeout or disconnect closes the sending boundary but
does not cancel the owned application task. In-flight driver/service work settles
before the route checks activity and rolls back. The whole ASGI application task
remains tracked, keeping FastAPI dependencies and the transaction owner alive until
cleanup completes. Ordinary unmarked handlers retain cooperative cancellation.
Checking the monotonic clock also prevents a delayed timer or a controller that
catches cancellation from bypassing the pre-commit boundary.

| Interruption boundary                                  | Database outcome                                             |
| ------------------------------------------------------ | ------------------------------------------------------------ |
| Before work or after delayed acquisition               | Reject before business SQL                                   |
| After writes, before the final activity check          | Roll back when owned work settles                            |
| After commit has begun                                 | Unconfirmed until the database/driver settles; it may commit |
| MySQL committed but acknowledgement was lost           | Data can be committed despite a client error or 408          |
| Commit confirmed, then cleanup or HTTP delivery failed | Data remains committed; suppress late responses              |

There is no atomic boundary between checking the deadline and the database
receiving COMMIT. An expiry or disconnect after the final check cannot revoke an
already-started commit. The application never retries a mutation automatically and
never interprets 408, disconnect, or driver failure as proof of rollback. Clients
must retain the original key/input for [durable retries](architecture.md#request-idempotency); unkeyed
mutations have no replay guarantee.

Database errors propagate through SQLAlchemy's rollback/close paths. A broken
connection is invalidated rather than returned as a usable lease. A subsequent
request owns a fresh session. Rollback/close failures remain errors, not evidence
of successful cleanup or rollback. Cleanup is not rejected merely because the
request deadline expired. Server cancellation and the final
[shutdown deadline](deployment.md#graceful-shutdown) still apply; request expiry does not promise to
cancel a SQL statement or bound how long an unresponsive driver takes to settle.

## Request idempotency

### Client contract

Create, PATCH, PUT and POST deletion accept an optional `Idempotency-Key` header.
Use one opaque value of 1–128 printable ASCII characters, without whitespace or
commas. Invalid or duplicate fields return 400. Without a key, mutations execute
normally and duplicate creation remains possible. Choose a new key for each new
intended mutation; retain the same key and input when retrying it.

| Retry                                           | Result                                                |
| ----------------------------------------------- | ----------------------------------------------------- |
| Same key, operation, caller and validated input | Original successful status and exact JSON bytes       |
| Same scope/key with changed input               | 409                                                   |
| Matching request still processing               | 409                                                   |
| Failed attempt                                  | No completed replay retained; transaction rolled back |
| Expired result                                  | Key may execute again                                 |

Retain the original payload, including `expected_version`, on retries. Replay is
checked before the controller runs, so it remains available after later updates or
deletion and does not advance versions again. Results live for 24 hours from database
completion; replay does not extend expiry. This is a retry mechanism, not authentication.

### Shared route infrastructure

Use `ApplicationRoute` (or `FlexibleRouter(route_class=ApplicationRoute)`) and declare
both transaction ownership and an idempotency policy. Business services/repositories
need no retry logic. For example:

```python
@router.post("", response_model=WidgetResponse, status_code=201)
@transactional
@idempotent(
    operation="widgets.create",
    route="POST /api/v1/widgets",
)
async def create(
    payload: CreateWidgetRequest,
    service: WidgetService = Depends(get_widget_service),
) -> WidgetResponse:
    widget = await service.create(payload)

    return WidgetResponse.model_validate(widget)
```

Import `transactional` from `app.common.handlers.application_route` and `idempotent`
from `app.common.models.idempotency_model`. The widget names illustrate another domain.
Route identity defaults to the matched canonical route template and HTTP method. Case and slash aliases share the same persisted scope; parameter values remain in the fingerprint. An explicit `route` overrides this default for compatibility. Import `PUBLIC_IDEMPOTENCY_SCOPE` from `app.common.models.idempotency_model`.

Caller scope defaults to `PUBLIC_IDEMPOTENCY_SCOPE`. Override `caller_scope` with an explicit scope or a
function returning an authenticated identity from `request.state` after normal
authorization dependencies run. Header values alone do not establish identity.

Operation and route template are stable declarations; do not put a concrete resource
ID in the scope. The request fingerprint includes validated body, path and query
values instead. Reusing a PATCH key for another item therefore conflicts. Different
operations and callers have separate scopes. The namespace hashes application name
and database name, excluding host aliases and application version; keep it stable
across replicas and retries.

Declare business inputs with FastAPI/Pydantic models and parameters. Do not read
additional raw business input inside keyed handlers. Input normalization sorts object
keys, preserves exact Decimal values, fingerprints real masked/excluded input
fields, excludes computed properties and includes non-null defaults; omitted optional fields remain distinct from explicit null. Dependencies
still run normally, including authorization; replay skips the controller/service work.
Asynchronous and synchronous endpoints are supported.

### Supported declarations and fingerprint compatibility

Declare body/path/query inputs directly on the endpoint. Registration rejects:

- Body/path/query fields hidden in dependencies, including transitive dependencies.
- Undeclared URL path parameters or duplicate aliases within an input category.
- Direct raw `Request`/`HTTPConnection`, header or cookie inputs on the endpoint.
- Non-JSON bodies, including form/file declarations.

Dependencies can provide services, sessions and authorization using Request, headers
or cookies, but must not construct hidden mutation input. Move business inputs to
explicit endpoint parameters. Caller-scope callbacks can still use the authenticated
request state. This is a declaration guard; it does not inspect arbitrary dependency
code for raw body access or side effects.

The frozen encoding is `quickapi-json-v1`, with fixed
[reference vectors](../tests/fixtures/idempotency_fingerprints_v1.json). The label is
not an added hash prefix, so existing stored fingerprints and replay scopes remain
unchanged. Vectors specify canonical UTF-8 text and SHA-256 for ordering, Unicode,
exact numbers, omitted/null fields and actual secret/excluded input values.

Treat changes to normalization, encoding, namespace and scope hashing as persisted
compatibility changes. Do not regenerate vectors to make a refactor pass, or simply
bump the scope namespace: that can hide old results and execute a committed mutation
again. A future format change must preserve existing scope lookup and verify retained
records with their original format, introducing explicit stored format metadata and
legacy readers before new writes if necessary. Test replay across versions throughout
the 24-hour retention window before removing compatibility support.

### Persistence and cleanup

The route owner pins one MySQL connection, acquires a non-waiting advisory lock,
and retains it through commit settlement. Domain writes and the prepared response
commit in the same transaction. The original JSON is replayed without serialization.
Only buffered successful JSON responses are retained; streams/background tasks are
unsupported. Invalid output, oversized responses and preparation failures roll back
both the mutation and claim. Uncertain lock ownership or failed release retires the
connection. Timeout/disconnect does not undo a COMMIT already started: retry the same
key/input to reconcile the result, rather than changing the payload or revision.

`IdempotencyCleanupService` is lifecycle-owned after the database service, stops
admitting cleanup on quiesce, and settles its active batch before database teardown.
It runs hourly, shares overlapping work per instance and rechecks expiry in SQL so
multiple replicas can clean safely. Expired keys also get reclaimed on use.

## Database lifecycle

### Contract

Startup verifies the committed Alembic revision using the application engine.
Migrations are applied only by explicit migration commands. After startup,
`/ready` checks connectivity through the same pool used by item operations.
`/health` reports process liveness without consulting MySQL.

The public readiness response retains `ready`, `status`, and `timestamp`. Database
errors, connection details, and dependency timings are not exposed. Probes work
when documentation, metrics, and diagnostics endpoints are disabled.

### Startup

Migration verification has a deadline covering connection acquisition and revision
inspection. A missing, incompatible, or unavailable revision history prevents
startup. Timeout, cancellation, or verification failure disposes the engine before
the failure propagates. The failing service owns this cleanup because it has not
yet joined the lifecycle handler's successfully started services.

Verification does not apply migrations, create missing history, or repair schema
drift. A failed initial startup requires another application start after the
problem is resolved. Runtime recovery does not rerun startup migration checks.
The asynchronous deadline does not preempt synchronous filesystem/CPU work.

### Runtime probes

Checks run on demand; there is no background monitor or retry loop.

1. A stopped database service reports unavailable without opening a connection.
2. Callers share an active probe, including its acquisition and cleanup. Cancellation
   of one caller does not cancel the shared operation.
3. Otherwise, a cached result is reused until its monotonic expiry. Both successful
   and unsuccessful results are cached.
4. A new probe acquires one application-pool lease and executes `SELECT 1`. Its
   deadline covers acquisition, SQL, and normal connection return.
5. Success permits readiness 200 when startup and other dependencies are healthy.
   Failure or timeout produces readiness 503. Successful leases are returned; a
   failed or cancelled active probe invalidates only its own connection.

The lifecycle handler retains its independent one-second dependency timeout. If
configured readiness work takes longer, a caller can receive an unavailable result
while the single shared probe finishes. Further callers cannot accumulate probes
behind that operation. Cleanup remains owned until completion. Python cancellation
is cooperative; real-driver tests establish the supported MySQL behavior.

### Outages and recovery

A connectivity failure does not dispose the shared application pool or restart the
API. Failed/stale probe connections are retired; later checks can acquire replacement
connections after cache expiry. A stalled connection is invalidated on cancellation
so unread protocol data cannot be reused. Other requests' leases are unaffected.

Cached success can briefly report readiness during an outage. Detection time includes
the remaining cache lifetime, probe deadline, deployment polling interval, and failure
thresholds. Readiness is evidence of current connectivity, not a guarantee that the
next business operation will succeed. Business requests are not automatically retried,
and a failed in-flight mutation is not replayed automatically. A caller can reconcile
an uncertain keyed result through [durable mutation retries](architecture.md#request-idempotency).

Stopping the database service clears the cache, cancels and awaits its active probe,
then disposes the engine. Readiness remains unavailable afterward. This does not
provide application-wide traffic withdrawal, mutation draining, or a final shutdown
deadline; those are separate lifecycle requirements.

## API contracts

### Items

| Method | Route                       | Success | Behavior                                                     |
| ------ | --------------------------- | ------- | ------------------------------------------------------------ |
| POST   | `/api/v1/items`             | 201     | Create and return an item                                    |
| GET    | `/api/v1/items`             | 200     | Return a filtered, paginated collection                      |
| GET    | `/api/v1/items/{id}`        | 200     | Retrieve an item                                             |
| PATCH  | `/api/v1/items/{id}`        | 200     | Update supplied fields                                       |
| PUT    | `/api/v1/items/{id}`        | 200     | Replace using the full input model                           |
| POST   | `/api/v1/items/{id}/delete` | 200     | Delete with a revision precondition; return the removed item |

IDs are exactly 16 ASCII alphanumeric characters, including upper/lowercase letters. Existing hexadecimal IDs remain valid. Invalid IDs/payloads return 422; missing items return 404. Responses include `id`, `version`, `name`, `price`, `description`, `createdAt`, and `updatedAt`.

Create/replace require `name` (1–120 characters) and `price`. `description` is optional, nullable, and at most 500 characters. Omitting it on PUT resets it to null. PATCH requires at least one recognized supplied field, rejects explicit null for `name`/`price`, and allows null to clear `description`.

Prices must be between `0.01` and `99999999.99`, with at most two decimal places. Accept JSON numbers or unsigned plain decimal strings such as `"12.34"`. Strings reject whitespace, signs, exponent notation and more than two fractional digits, including trailing zeros. Boolean, non-finite, zero, negative, excessive-precision and out-of-range values return 422 without rounding. JSON numeric spelling is interpreted after parsing, so numeric `1.230` is accepted as `1.23`.

Models, services and MySQL `Numeric(10, 2)` storage retain exact `Decimal` values. Responses serialize prices as JSON numbers and validate the same range and precision. Python/ORM timestamp attributes remain `created_at` and `updated_at`; JSON uses the aliases above.

Existing rows outside the accepted price
range fail response validation; repair them explicitly before reading them through
the API. Development data is never reset automatically.

### Mutation revisions

Every item starts at `version: 1`. PATCH, PUT and POST deletion require
`expected_version` from the caller's last read: a numeric integer from 1 through 4294967295. Boolean, string, null, fractional and out-of-range revisions return 422.
As in Express, parsed numeric `1.0` denotes revision 1. PATCH also requires at least
one recognized editable field; a revision alone is not an edit.

The transaction locks the row and compares its revision; UPDATE and DELETE also
include the expected revision in SQL. Every accepted PATCH/PUT advances the version
once, including unchanged-value edits. Updates at the maximum revision return 409;
deletion of that revision remains allowed and returns its final persisted resource.

Missing items return 404 with `No item exists with the provided identifier.` Stale
or exhausted revisions return 409 with `Item version conflict; reload the item before
retrying.` Deletion uses the versioned POST action;
use `POST /api/v1/items/{id}/delete` with JSON such as `{"expected_version": 2}`.
Successful deletion retries without a key return 404; keyed retries replay the original result.

Item routes and named system endpoints accept either trailing-slash spelling through
the shared router, without redirecting or duplicate controller declarations. OpenAPI
lists only the canonical spelling; the application root `/` is registered once.
Static path text matches without case sensitivity; parameter values keep their
original case. GET endpoints also accept HEAD, returning the selected handler's
status and headers without response body bytes. Explicit HEAD handlers take priority.
The canonical collection route has no trailing slash. Apply pending migrations
before startup; the revision migration initializes existing rows to revision 1.

### Collection queries

| Query       | Default | Constraint                                                             |
| ----------- | ------- | ---------------------------------------------------------------------- |
| `page`      | 1       | Integer 1–9007199254740991; calculated offset must also fit this range |
| `limit`     | 25      | Integer 1–100                                                          |
| `sort`      | `price` | `name`, `price`, or `createdAt`                                        |
| `order`     | `ASC`   | Case-insensitive `ASC` or `DESC`; normalized internally                |
| `search`    | Absent  | Case-insensitive SQL LIKE over name or description                     |
| `min_price` | Absent  | Same exact price rules; cannot exceed `max_price`                      |
| `max_price` | Absent  | Same exact price rules                                                 |

Both price bounds are inclusive. The JSON envelope contains `data`, `total`, `page`, and `limit`. `total_pages` is a Python property, not a serialized field. Search trims surrounding whitespace and includes SQL LIKE `%` and `_` wildcard semantics.

Sort by the selected column followed by item ID in the same direction. Equal-value
pages are deterministic while data is unchanged; concurrent writes can still move
items between offset-based pages. The public `createdAt` sort token maps to the ORM
`created_at` attribute; the old `created_at` query token is rejected.

Repeated query parameters return 422, even when both values are identical, rather
than silently choosing one. Invalid page/offset bounds are rejected before SQL.

### Error contract

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
message; unhandled exceptions return only `Internal Server Error`. Malformed JSON
returns `400` with `Malformed JSON request body.`; valid JSON with invalid fields
continues to return `422`. OpenAPI replaces
FastAPI's default validation schema with this contract.

### Transport and mutation boundaries

JSON mutations should send `Content-Type: application/json`. Middleware may reject requests before routing for body/header limits, content type, method, rate, or timeout policies. [Application assembly](../app/config/application.py) defines active limits and CORS policy; [Architecture](architecture.md#request-lifecycle-and-middleware-order) records their order.

The process-local limiter defaults to 200 admitted requests in the preceding 60 seconds per resolved client, with bounded client storage. Quota exhaustion returns 429; new identities at storage capacity receive 503. Both include positive `Retry-After` and the existing error envelope. Operational routes and preflights share the quota; favicon GET/HEAD is exempt. See [rate limiting](security.md#rate-limiting) for settings, response details, and process/CORS boundaries.

Item controllers delegate to services and validate their results into response models. Repository
mutations participate in the request-owned transaction and never commit
independently. The route owner commits after service execution and buffered JSON
preparation; see [Mutation transactions](architecture.md#mutation-transactions). Optimistic concurrency is enforced. Declared item mutations optionally accept
`Idempotency-Key` for durable retries. Matching completed requests replay the original
successful JSON/status for 24 hours, including after later item changes or deletion.
Invalid/duplicate keys return 400; changed input and in-progress keys return 409.
Failures are not retained. Keep the original payload and `expected_version` on retries;
see [Durable mutation retries](architecture.md#request-idempotency) for scopes, cleanup and limits.

Operational payloads and access boundaries are documented in [Deployment](deployment.md#operational-endpoints).

### Public readiness

`GET /ready` returns only `ready`, `status`, and UTC `timestamp`, with HTTP 200 or
503 according to startup/dependency health. Dependency names and timings are not
part of the public probe contract. `/health` remains a separate dependency-free liveness check. Operational
exposure flags do not disable either probe.

## Adding a capability

Declare HTTP models and route policy in controllers, application decisions in
services, and reusable persistence in repositories. Pass the caller-owned session;
HTTP mutations do not independently commit. Validate response models before commit.
Choose version and replay semantics explicitly and test authorization where present,
validation, rollback, timeout/disconnect, retry, concurrency, and cleanup boundaries.

Keep the README as the entry point and use only seven reference guides: Setup,
Architecture, Configuration, Testing, Security, Deployment, and Backlog. Describe
current supported behavior in the present tense. Keep implementation plans and
unresolved work in Backlog; do not retain milestone tables, per-release diaries,
or transient pass counts. Update links and examples when contracts change.
