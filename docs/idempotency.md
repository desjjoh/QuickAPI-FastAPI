# Durable mutation retries

[Documentation index](../README.md#documentation)

## Client contract

Create, PATCH, PUT and POST deletion accept an optional `Idempotency-Key` header.
Use one opaque value of 1–128 printable ASCII characters, without whitespace or
commas. Invalid or duplicate fields return 400. Without a key, mutations execute
normally and duplicate creation remains possible. Choose a new key for each new
intended mutation; retain the same key and input when retrying it.

| Retry | Result |
| --- | --- |
| Same key, operation, caller and validated input | Original successful status and exact JSON bytes |
| Same scope/key with changed input | 409 |
| Matching request still processing | 409 |
| Failed attempt | No completed replay retained; transaction rolled back |
| Expired result | Key may execute again |

Retain the original payload, including `expected_version`, on retries. Replay is
checked before the controller runs, so it remains available after later updates or
deletion and does not advance versions again. Results live for 24 hours from database
completion; replay does not extend expiry. This is a retry mechanism, not authentication.

## Shared route infrastructure

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

## Supported declarations and fingerprint compatibility

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

## Persistence and cleanup

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

| Optional environment override | Default | Bounds |
| --- | --- | --- |
| `IDEMPOTENCY_MAX_RESPONSE_BYTES` | 65536 | 1–65536 bytes; lowering it does not invalidate existing valid replays |
| `IDEMPOTENCY_CLEANUP_BATCH_SIZE` | 100 | 1–1000 rows |
| `IDEMPOTENCY_CLEANUP_MAX_BATCHES` | 10 | 1–100; batch size × batches ≤ 10000 |

The defaults remove at most 1000 expired records per sweep. `idempotency-key` is in
the default CORS request-header list and sanitizer allowlist. Custom browser header
lists must retain it for keyed requests. There is no response key header to expose.

Apply migration `0003_request_idempotency` before startup; see [Migrations](migrations.md).
Downgrade removes replay history but preserves domain data. Do not mix old writers
with callers relying on durable retries. Local qualification and CI boundaries are
recorded in [Verification](verification.md).
