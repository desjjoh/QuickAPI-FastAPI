# Controllers and services

[Documentation index](../README.md#documentation)

## Shared boundary

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

## Item operations

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
[transaction contract](transactions.md) also covers timeout, disconnect, cleanup
and uncertain commit outcomes. Non-HTTP callers must supply a session and explicitly
own any mutation transaction themselves.

## System operations

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

## Verification

Item behavior unit tests live under `tests/unit/api/v1/items/services`. System
service tests cover dependency-independent liveness, timestamp calculation and
readiness decisions. Controller tests reject invalid service output for item
operations and system payloads. HTTP checks preserve public contracts and readiness status
mapping. MySQL tests verify that service dependencies share the mutation owner,
response preparation failures roll back, and expiry/shutdown behavior is retained.

```powershell
python -m pytest -q tests/unit/api --no-cov
python -m scripts.test_db test
```
