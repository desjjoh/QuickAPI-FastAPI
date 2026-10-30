# Mutation transaction ownership

[Documentation index](../README.md#documentation)

## Route contract

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

## Execution order

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

## Expiry and commit outcomes

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

| Interruption boundary | Database outcome |
| --- | --- |
| Before work or after delayed acquisition | Reject before business SQL |
| After writes, before the final activity check | Roll back when owned work settles |
| After commit has begun | Unconfirmed until the database/driver settles; it may commit |
| MySQL committed but acknowledgement was lost | Data can be committed despite a client error or 408 |
| Commit confirmed, then cleanup or HTTP delivery failed | Data remains committed; suppress late responses |

There is no atomic boundary between checking the deadline and the database
receiving COMMIT. An expiry or disconnect after the final check cannot revoke an
already-started commit. The application never retries a mutation automatically and
never interprets 408, disconnect, or driver failure as proof of rollback. Clients
must retain the original key/input for [durable retries](idempotency.md); unkeyed
mutations have no replay guarantee.

Database errors propagate through SQLAlchemy's rollback/close paths. A broken
connection is invalidated rather than returned as a usable lease. A subsequent
request owns a fresh session. Rollback/close failures remain errors, not evidence
of successful cleanup or rollback. Cleanup is not rejected merely because the
request deadline expired. Server cancellation and the final
[shutdown deadline](shutdown.md) still apply; request expiry does not promise to
cancel a SQL statement or bound how long an unresponsive driver takes to settle.

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

[Expiry and uncertainty tests](../tests/integration/database/test_mutation_expiry.py)
use loopback Uvicorn and the guarded disposable MySQL database. They cover all four
mutation methods after writes, real HTTP disconnects, delayed pool acquisition,
caught cancellation, post-commit cleanup failure, and recovery. A packet-framed
test relay holds real INSERT results and COMMIT commands/acknowledgements; separate
observer sessions prove when rows are committed. Connection loss checks verify
invalidation, owner cleanup, capacity recovery, and absence of automatic replay.
Rollback-specific barriers drop the connection before MySQL receives ROLLBACK or
after MySQL processes it but before the acknowledgement reaches the driver. They
verify that an already-written mutation remains absent, the broken server session
disappears, and a queued request receives a replacement lease only after rollback
settles. [Process checks](shutdown.md#verification) also combine an expired marked
mutation with shutdown and verify dependency lifetime and final-deadline behavior.

Transaction ownership alone does not guarantee delivery or establish query
cancellation. Revision preconditions and the optional durable retry policy build on
this boundary; see [API contracts](api-contracts.md) and [Durable mutation retries](idempotency.md).

See [Verification](verification.md) for candidate-specific results.

## Durable keyed mutations

Routes opt in with an explicit `@idempotent` policy alongside `@transactional`.
FastAPI still validates inputs and prepares responses. The route wrapper acquires
the key claim after validation, before controller execution, and stores the exact
prepared successful response in the same transaction as the domain write. Matching
replays return stored bytes without calling the controller or checking current item
versions. Keyed execution pins a connection through commit and advisory-lock release;
uncertain ownership is retired rather than returned to the pool. See
[Durable mutation retries](idempotency.md) for the shared contract.
