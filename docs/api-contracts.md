# API contracts

[Documentation index](../README.md#documentation)

## Scope and source of truth

This guide describes currently implemented behavior. The
[item specification](item-contract-specification.md) records the agreed Express
alignment target; it does not change the running contract until implemented.

When `DOCS_ENABLED=true`, the app exposes `/docs`, `/redoc`, and `/openapi.json`; documentation defaults off in production. The schema reflects the registered endpoint surface. See [operational exposure](operational-exposure.md). Contracts live in the [item controller](../app/api/v1/items/controllers/item_controller.py), [item models](../app/api/v1/items/models), and [shared models](../app/common/models). No account, authentication, or article routes are implemented.

## Items

| Method | Route                | Success | Behavior                                |
| ------ | -------------------- | ------- | --------------------------------------- |
| POST   | `/api/v1/items/`     | 201     | Create and return an item               |
| GET    | `/api/v1/items/`     | 200     | Return a filtered, paginated collection |
| GET    | `/api/v1/items/{id}` | 200     | Retrieve an item                        |
| PATCH  | `/api/v1/items/{id}` | 200     | Update supplied fields                  |
| PUT    | `/api/v1/items/{id}` | 200     | Replace using the full input model      |
| DELETE | `/api/v1/items/{id}` | 200     | Return the deleted item                 |

IDs are exactly 16 ASCII alphanumeric characters, including upper/lowercase letters. Existing hexadecimal IDs remain valid. Invalid IDs/payloads return 422; missing items return 404. Responses include `id`, `name`, `price`, `description`, `createdAt`, and `updatedAt`.

Create/replace require `name` (1–120 characters) and `price`. `description` is optional, nullable, and at most 500 characters. Omitting it on PUT resets it to null. PATCH requires at least one recognized supplied field, rejects explicit null for `name`/`price`, and allows null to clear `description`.

Prices must be between `0.01` and `99999999.99`, with at most two decimal places. Accept JSON numbers or unsigned plain decimal strings such as `"12.34"`. Strings reject whitespace, signs, exponent notation and more than two fractional digits, including trailing zeros. Boolean, non-finite, zero, negative, excessive-precision and out-of-range values return 422 without rounding. JSON numeric spelling is interpreted after parsing, so numeric `1.230` is accepted as `1.23`.

Models, services and MySQL `Numeric(10, 2)` storage retain exact `Decimal` values. Responses serialize prices as JSON numbers and validate the same range and precision. Python/ORM timestamp attributes remain `created_at` and `updated_at`; JSON uses the aliases above.

These rules require no schema migration. Existing rows outside the accepted price
range fail response validation; repair them explicitly before reading them through
the API. Development data is never reset automatically.

## Collection queries

| Query       | Default | Constraint                                         |
| ----------- | ------- | -------------------------------------------------- |
| `page`      | 1       | Integer 1–9007199254740991; calculated offset must also fit this range |
| `limit`     | 25      | Integer 1–100                                      |
| `sort`      | `price` | `name`, `price`, or `createdAt`                     |
| `order`     | `ASC`   | Case-insensitive `ASC` or `DESC`; normalized internally |
| `search`    | Absent  | Case-insensitive SQL LIKE over name or description |
| `min_price` | Absent  | Same exact price rules; cannot exceed `max_price` |
| `max_price` | Absent  | Same exact price rules                            |

Both price bounds are inclusive. The JSON envelope contains `data`, `total`, `page`, and `limit`. `total_pages` is a Python property, not a serialized field. Search trims surrounding whitespace and includes SQL LIKE `%` and `_` wildcard semantics.

Sort by the selected column followed by item ID in the same direction. Equal-value
pages are deterministic while data is unchanged; concurrent writes can still move
items between offset-based pages. The public `createdAt` sort token maps to the ORM
`created_at` attribute; the old `created_at` query token is rejected.

Repeated query parameters return 422, even when both values are identical, rather
than silently choosing one. Invalid page/offset bounds are rejected before SQL.

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

Item controllers delegate to services and validate their results into response models. Repository
mutations participate in the request-owned transaction and never commit
independently. The route owner commits after service execution and buffered JSON
preparation; see [Mutation transactions](transactions.md). No optimistic concurrency
token, idempotency-key contract, or replay protection exists. Avoid automatic
mutation retries unless the caller can reconcile an uncertain result.

Operational payloads and access boundaries are documented in [Deployment](deployment.md#application-lifespan-and-operational-endpoints).

## Public readiness

`GET /ready` returns only `ready`, `status`, and UTC `timestamp`, with HTTP 200 or
503 according to startup/dependency health. Dependency names and timings are not
part of the public probe contract. `/health` remains a separate dependency-free liveness check. Operational
exposure flags do not disable either probe.
