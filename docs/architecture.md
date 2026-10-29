# Architecture

[Documentation index](../README.md#documentation)

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
5. Controllers validate inputs, borrow a database session, call the repository, and
   serialize a declared response model.

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

## Persistence and migrations

`get_session()` creates one async session per dependency invocation and closes it
after the response dependency scope completes. Read queries do not commit. Each
repository mutation owns its transaction: it flushes and refreshes, commits on
success, and rolls back on any failure so the session is safe to close or reuse.

[Alembic migrations](migrations.md) own schema creation and changes. The API checks
that the connected database revision matches the single source head before startup
completes; it does not apply migrations or call `metadata.create_all()`. Apply
`python -m alembic upgrade head` explicitly before starting native Python. Compose
uses a one-shot migration service before API startup. Revision equality does not
establish that manually edited tables match the models; schema comparison and
data/rollback compatibility need separate evidence.

## Lifecycle and extension rules

[Application assembly](../app/config/application.py) registers the database service and composes middleware, exception handlers, and routes. [LifecycleHandler](../app/common/handlers/lifecycle_handler.py) starts services and stops successfully started services in reverse order, including rollback after partial startup failure.

Keep HTTP validation/serialization in API models/controllers, queries and commit/rollback boundaries in repositories, and transport policies in middleware. Add services when domain orchestration needs them. Register long-lived dependencies with the lifecycle handler and test readiness and cleanup failures.

Update [API contracts](api-contracts.md) when routes/models change, [Development](development.md) when configuration changes, and [Deployment](deployment.md) when runtime behavior changes. Track unresolved limitations in [Backlog](backlog.md).

## Request deadlines

See [Request deadlines and streaming](request-timeouts.md) for the pure-ASGI response state boundary, bounded receive ownership, cancellation/cleanup limits, and Express-aligned HTTP outcomes. It does not implement TCP header deadlines or mutation rollback guarantees.


## Documentation conventions

Reference guides describe the current supported behavior in the present tense.
Document configuration, contracts, commands, and limitations directly, without
implementation chronology, phase-completion notes, or descriptions of superseded
behavior. Keep implementation plans/status in the roadmap, milestones, and backlog;
write verification reports as final documents organized by scope, source identity,
results, and limitations. Verification reports also avoid phase-completion narratives.
Update related examples and links when a contract changes.
