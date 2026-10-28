# API contracts

[Documentation index](../README.md#documentation)

## Scope and source of truth

When `DOCS_ENABLED=true`, the app exposes `/docs`, `/redoc`, and `/openapi.json`; documentation defaults off in production. The schema reflects the registered endpoint surface. See [operational exposure](operational-exposure.md). Contracts live in the [item controller](../app/api/v1/items/controllers/item_controller.py), [item models](../app/api/v1/items/models), and [shared models](../app/common/models). No account, authentication, or article routes are implemented.

## Items

| Method | Route | Success | Behavior |
| --- | --- | --- | --- |
| POST | `/api/v1/items/` | 201 | Create and return an item |
| GET | `/api/v1/items/` | 200 | Return a filtered, paginated collection |
| GET | `/api/v1/items/{id}` | 200 | Retrieve an item |
| PATCH | `/api/v1/items/{id}` | 200 | Update supplied fields |
| PUT | `/api/v1/items/{id}` | 200 | Replace using the full input model |
| DELETE | `/api/v1/items/{id}` | 200 | Return the deleted item |

IDs are exactly 16 lowercase hexadecimal characters. Invalid IDs/payloads return 422; missing items return 404. Responses include `id`, `name`, `price`, `description`, `created_at`, and `updated_at`.

Create/replace require `name` (1–120 characters) and `price` (a non-negative float). `description` is optional, nullable, and at most 500 characters. Omitting it on PUT resets it to null. PATCH requires at least one recognized supplied field, rejects explicit null for `name`/`price`, and allows null to clear `description`.

Storage uses `Numeric(10, 2)`, but request models do not enforce matching precision/range. Exact decimal validation and database-engine parity are unresolved; see [Backlog](backlog.md).

## Collection queries

| Query | Default | Constraint |
| --- | --- | --- |
| `page` | 1 | Integer ≥ 1 |
| `limit` | 20 | Integer 1–100 |
| `sort` | `price` | `name`, `price`, or `created_at` |
| `order` | `asc` | `asc` or `desc` |
| `search` | Absent | Case-insensitive SQL LIKE over name or description |
| `min_price` | Absent | Non-negative; cannot exceed `max_price` |
| `max_price` | Absent | Non-negative |

The JSON envelope contains `data`, `total`, `page`, and `limit`. `total_pages` is a Python property, not a serialized field. Search includes SQL LIKE `%` and `_` wildcard semantics. Sorting has no unique tie-breaker, so equal values do not guarantee stable page ordering.

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

## Transport and mutation boundaries

JSON mutations should send `Content-Type: application/json`. Middleware may reject requests before routing for body/header limits, content type, method, rate, or timeout policies. [Application assembly](../app/config/application.py) defines active limits and CORS policy; [Architecture](architecture.md#request-lifecycle-and-middleware-order) records their order.

The process-local limiter defaults to 200 admitted requests in the preceding 60 seconds per resolved client, with bounded client storage. Quota exhaustion returns 429; new identities at storage capacity receive 503. Both include positive `Retry-After` and the existing error envelope. Operational routes and preflights share the quota; favicon GET/HEAD is exempt. See [rate limiting](rate-limiting.md) for settings, response details, and process/CORS boundaries.

Repository mutations commit before returning. No optimistic concurrency token, idempotency-key contract, or replay protection exists. Avoid automatic mutation retries unless the caller can reconcile an uncertain result. Implement and test guarantees before documenting them.

Operational payloads and access boundaries are documented in [Deployment](deployment.md#application-lifespan-and-operational-endpoints).


## Public readiness

`GET /ready` returns only `ready`, `status`, and UTC `timestamp`, with HTTP 200 or
503 according to startup/dependency health. Dependency names and timings are not
part of the public probe contract. `/health` remains a separate dependency-free liveness check. Operational
exposure flags do not disable either probe.
