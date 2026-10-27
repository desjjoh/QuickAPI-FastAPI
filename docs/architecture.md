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

## Lifecycle and extension rules

[Application assembly](../app/config/application.py) registers the database service and composes middleware, exception handlers, and routes. [LifecycleHandler](../app/common/handlers/lifecycle_handler.py) starts services and stops successfully started services in reverse order, including rollback after partial startup failure.

Keep HTTP validation/serialization in API models/controllers, queries and commit/rollback boundaries in repositories, and transport policies in middleware. Add services when domain orchestration needs them. Register long-lived dependencies with the lifecycle handler and test readiness and cleanup failures.

Update [API contracts](api-contracts.md) when routes/models change, [Development](development.md) when configuration changes, and [Deployment](deployment.md) when runtime behavior changes. Track unresolved limitations in [Backlog](backlog.md).

## Request deadlines

See [Request deadlines and streaming](request-timeouts.md) for the pure-ASGI response state boundary, bounded receive ownership, cancellation/cleanup limits, and Express-aligned HTTP outcomes. It does not implement TCP header deadlines or mutation rollback guarantees.
