# Architecture

[Documentation index](../README.md#documentation)

[Graceful shutdown](shutdown.md) defines request admission, draining, deadlines,
entrypoint ownership, and process verification.

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
`app/config/application.py`. [Services](services.md) describes the shared item and
system boundary and session ownership.

## Flexible route spelling

Item and system controllers use [FlexibleRouter](../app/common/handlers/flexible_router.py)
to accept named HTTP endpoints with or without a trailing slash, without redirects.
Controllers declare each operation once. The router registers the canonical path
first and hides the alternate spelling from OpenAPI. URL generation selects the
canonical route. Nested router inclusion copies existing routes without generating
another pair; response models, status codes, dependencies and route classes survive.

Use `""` for a collection root mounted beneath a prefix, such as `/api/v1/items`.
An explicit `"/"` remains a single root route, as used by the system greeting.
Named paths such as `/health` and `/items/{id}` receive both spellings. Item routes
retain `ApplicationRoute` and their transaction markers. Operational exposure
settings protect both spellings. Framework-provided documentation routes retain
their normal FastAPI routing behavior.

## Request lifecycle and middleware order

Starlette wraps middleware in reverse registration order. Consequently, the last
middleware added in `create_app()` is the first to see a request. The effective
inbound order is:

```text
request outcome → server error handler → cleanup → trusted proxy → request context
→ request logging → metrics → header limits → security headers → rate limit → CORS
→ body limit → content type → header sanitization
→ method allowlist → timeout → operational exposure → routing/controller
```

Responses unwind through the same layers in reverse. This is intentional:

1. One request-outcome observer wraps Starlette's server error handler so final
   500 responses and transport failures are observed. Cleanup clears request context
   even after failures.
2. Explicit IP/CIDR proxy trust resolves client identity before request context.
   Request identity is established before logging and returned as `X-Request-ID`.
3. Parsed-header budgets run before preflight responses and sanitizer filtering;
   transport and security checks reject unsafe requests before domain code runs.
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
The [bounded rolling-window limiter](rate-limiting.md) is process-local, with
fixed-capacity timestamp rings and expiry-ordered client storage. Admission occurs
before CORS preflights and later policy rejections, while raw-header budgets remain
ahead of it. Shared storage is required for a global quota across workers/replicas.

[Metrics and request outcomes](deployment.md#metrics-and-request-outcomes) defines
labels, exclusions, units, and the dashboard migration. Declared route templates
include mount prefixes; concrete IDs, query values, and unknown paths never become
access-log routes or metric labels. [Logging](logging.md) uses DEBUG for successful requests, WARNING for client errors
and aborts, and ERROR for server failures. Console access records use `ABORTED` for
incomplete responses; production records expose the structured outcome.

[HTTP configuration](http-policy.md) defines defaults, environment overrides,
validation, proxy ownership, and the separate server receive-protection boundary.

[Operational exposure](operational-exposure.md) controls per-app route registration
and reserves disabled path families. Native docs are installed only when enabled.
Public readiness serializes no dependency details; internal service checking remains.

## Database capacity and transport

The shared [engine policy](database-settings.md) uses SQLAlchemy connection records with bounded async admission for MySQL. It caps connections/waiters, separates acquisition and connection setup budgets, and verifies TLS before returning encrypted connections. Other database drivers are rejected during configuration and engine creation. API startup, sessions, readiness, migrations, and disposable MySQL fixtures share transport configuration.

## Persistence and migrations

[Database readiness and recovery](database-lifecycle.md) uses one shared,
on-demand task per application database service, with monotonic result caching.
Probe cancellation retires only its connection; caller cancellation is isolated
from shared work. Startup revision verification has its own deadline and failure
cleanup. Runtime outages leave the engine available for replacement connections.

[Mutation transaction ownership](transactions.md) uses `ApplicationRoute` and
`@transactional` on the four item mutation endpoints. One fresh session/transaction
covers dependency resolution, service work, repository writes, and FastAPI
response validation/JSON rendering before commit. `get_session(request)` borrows
that owner for marked routes and creates/closes a read session for other routes.
Repositories require an active transaction and do not commit or roll back.
Item controllers delegate to `ItemService`; service work and model validation run
inside that same transaction boundary.

[Alembic migrations](migrations.md) own schema creation and changes. The API checks
that the connected database revision matches the single source head before startup
completes; it does not apply migrations or call `metadata.create_all()`. Apply
`python -m alembic upgrade head` explicitly before starting native Python. Compose
uses a one-shot migration service before API startup. Revision equality does not
establish that manually edited tables match the models; schema comparison and
data/rollback compatibility need separate evidence.

## Lifecycle and extension rules

[Application assembly](../app/config/application.py) registers the database service and composes middleware, exception handlers, and routes. [LifecycleHandler](../app/common/handlers/lifecycle_handler.py) starts services and stops successfully started services in reverse order, including rollback after partial startup failure.

Keep HTTP declarations and response-model validation in controllers, application logic in services, queries in repositories, and transport policies in middleware. Mutation commit/rollback belongs to the shared route owner. Register resources requiring startup/cleanup with the lifecycle handler and test readiness and cleanup failures.

Update [API contracts](api-contracts.md) when routes/models change, [Development](development.md) when configuration changes, and [Deployment](deployment.md) when runtime behavior changes. Track unresolved limitations in [Milestones](milestones.md).

## Request deadlines

See [Request deadlines and streaming](request-timeouts.md) for the pure-ASGI response state boundary, bounded receive ownership, cancellation/cleanup limits, and Express-aligned HTTP outcomes. It does not implement TCP header deadlines or mutation rollback guarantees.

## Documentation conventions

Reference guides describe the current supported behavior in the present tense.
Document configuration, contracts, commands, and limitations directly, without
implementation chronology, phase-completion notes, or descriptions of superseded
behavior. Keep implementation plans/status in Milestones;
write verification reports as final documents organized by scope, source identity,
results, and limitations. Verification reports also avoid phase-completion narratives.
Update related examples and links when a contract changes.
