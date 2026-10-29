# Mutation transaction ownership

[Documentation index](../README.md#documentation)

## Route contract

Mutation endpoints opt into a shared transaction boundary with `@transactional`.
Their router uses `ApplicationRoute`; the decorator marks the endpoint without
replacing its signature or implementing a middleware transaction around every
request. Controllers retain their existing item logic. No item service layer is
required by this contract.

```python
router = APIRouter(route_class=ApplicationRoute)


@router.post("/", response_model=ItemResponse, status_code=201)
@transactional
async def create(
    payload: ItemBase,
    db: AsyncSession = Depends(get_session),
) -> ItemResponse:
    item = await repo.create(db, item_in=model_to(ItemCreateData, payload))
    return ItemResponse.model_validate(item)
```

The item create, PATCH, PUT, and DELETE endpoints use this boundary. Unmarked
routes retain their normal FastAPI handler and dependency behavior. GET requests
are not wrapped in a mutation transaction; SQLAlchemy can still use a read
transaction for their queries.

## Execution order

1. Allocate a fresh request-owned `AsyncSession` with automatic transaction start
   disabled and begin one explicit transaction before resolving dependencies or
   calling the controller.
2. `get_session(request)` yields that same session. Repeated dependency resolution
   shares the owner rather than allocating another connection or transaction.
3. Run the controller's lookup, missing-resource checks, writes, flushes, refreshes,
   and response-model conversion inside the transaction.
4. Let FastAPI's normal handler perform response-model validation, serialization,
   alias/exclusion handling, status/header preparation, and JSON rendering.
5. Commit only after a buffered JSON response has been prepared. On successful
   commit, close the session and return that response to ASGI for delivery.

No response bytes are sent by the route owner before commit. Existing route
declarations remain the source for response models, status codes, and OpenAPI.
There is no copied serializer or second framework response pipeline. The original
item routes, fields, PATCH/PUT distinctions, DELETE confirmation, and error messages
retain their existing contracts.

## Failure and cleanup

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

## Repository callers

Repositories perform SQL, flushes, and refreshes. They require an active transaction
for mutations and never commit, roll back, or open a transaction independently.
Callers outside the HTTP route boundary must own the transaction explicitly:

```python
async with SessionLocal(autobegin=False) as db:
    async with db.begin():
        first = await repo.create(db, item_in={"name": "First", "price": 1})
        await repo.update(db, first, {"description": "Saved together"})
        await repo.create(db, item_in={"name": "Second", "price": 2})
```

All operations above commit together on context exit. A repository return value is
not evidence that a mutation has committed. Failure handling belongs to the caller's
transaction boundary. Tests can inject the session factory to point transactional
routes at their guarded MySQL engine; a separate session dependency must not replace
the owner with an independently managed transaction.

## Verification and limits

```powershell
python -m pytest -q tests/unit/common/handlers/test_application_route.py --no-cov
python -m scripts.test_db test
```

Real MySQL tests inject failures after SQL flush/refresh, during controller and
FastAPI response validation, during JSON rendering, and immediately before COMMIT.
Fresh observer sessions verify persisted outcomes. Other cases cover response
contracts, missing resources, shared dependencies, concurrent independent owners,
repository composition, rejection of deferred responses, and session cleanup.

A controlled failure before COMMIT is sent establishes rollback for that case. A
lost commit acknowledgement, cancellation during commit, post-commit cleanup or middleware failure, or
commit, or lost HTTP response can leave a committed mutation without client
confirmation. This boundary does not guarantee delivery, retry mutations, implement
idempotency, add optimistic concurrency, or establish query cancellation. Request
expiry and uncertain outcomes retain separate acceptance criteria. No database
migration or environment setting is introduced by transaction ownership.

See [Verification](verification.md) for candidate-specific results.
