# Item API specification

[Documentation index](../README.md#documentation)

## Reference and implementation status

QuickAPI-Express is the agreed template for the public item contract. The reference
checkout inspected on 2026-10-30 is commit
`eed860ca5d5d2549b6d7d1534063bfd54ff9b1bb`. Its item controllers, models,
repositories and idempotency policy define the behavior described here.

This specification is the implementation target. [Current API contracts](api-contracts.md)
documents the running FastAPI behavior until the corresponding alignment work is
implemented and verified. Agreement on this specification does not mean those
runtime changes have already shipped. [Milestones](milestones.md) tracks delivery.

The current implementation includes alphanumeric IDs, response timestamp aliases,
exact price validation and inclusive price filters. Pagination, revisions, deletion
and idempotency differences remain described in the current contract guide.

## Identity and resource shape

- Generate 16-character IDs using upper/lowercase ASCII letters and digits. Validate
  resource IDs against `[A-Za-z0-9]{16}`. Existing hexadecimal IDs remain valid.
- Expose `createdAt` and `updatedAt` as ISO8601 timestamps in item JSON. Python
  attributes may retain snake_case with explicit API aliases.
- Return `id`, `version`, `name`, `price`, `description`, `createdAt` and `updatedAt`.
- Keep name length 1–120 and description length at most 500. Description is nullable.
- Return prices as JSON numbers. Use Python `Decimal` internally for exact price
  handling; decimal response serialization must explicitly retain the number contract.

## Prices and filters

Accept prices from `0.01` through `99999999.99`, with at most two decimal places.
Reject excess precision rather than rounding it. Accept JSON numbers and unsigned
plain decimal strings, such as `"12.34"`. Strings with surrounding whitespace,
signs, exponent notation or more than two fractional digits are invalid.

Apply the same range and precision rules to `min_price` and `max_price`. Filters
are inclusive and a crossed range is invalid. Numeric input interpretation must be
qualified against the Express contract; string spelling rules are not a reason to
invent different behavior for already-parsed numeric inputs.

## Collection queries

- Default to `page=1`, `limit=25`, `sort=price` and `order=ASC`; maximum limit is 100.
- Accept `name`, `price` and `createdAt` as sort fields. Accept case-insensitive
  `ASC`/`DESC` and normalize internally.
- Require positive integer pages no greater than `9007199254740991`; the computed
  offset must also be within that safe-integer range.
- Sort by the selected column followed by item ID in the same direction.
- Preserve the `data`, `total`, `page`, `limit` envelope.
- Preserve trimmed SQL LIKE search over name and description, including wildcard
  behavior. Reject repeated scalar query parameters instead of silently choosing one.

## Mutations and revisions

| Operation | Route | Success | Required input |
| --- | --- | --- | --- |
| Create | `POST /api/v1/items` | 201 with item | Name and price; optional nullable description |
| Read/list | `GET /api/v1/items/{id}` or `/api/v1/items` | 200 | Valid path/query values |
| Partial update | `PATCH /api/v1/items/{id}` | 200 with item | `expected_version` and at least one recognized editable field |
| Replace | `PUT /api/v1/items/{id}` | 200 with item | `expected_version`, name and price; omitted description becomes null |
| Delete | `POST /api/v1/items/{id}/delete` | 200 with removed item | JSON body containing `expected_version` |

Use these canonical documented routes. Accept the collection's trailing-slash
spelling as an alias without a redirect, matching Express's non-strict routing.
The previous DELETE route is replaced by the versioned POST deletion
contract rather than retained as an unversioned mutation path.

Revisions are JSON integers, not booleans or numeric strings, starting at 1 and
ranging through `4294967295`. Every first accepted PATCH or
PUT increments the version once, including edits that leave values unchanged.
Compare revisions in SQL and reject overflow. Deletion returns the final persisted
representation and its version. Missing resources return 404; stale revisions
return 409; missing/invalid preconditions return 422.

Use the Express domain messages, including `No item exists with the provided identifier.`
and `Item version conflict; reload the item before retrying.` Preserve the shared
`status`, `message`, `timestamp` error envelope and deterministic input-validation
field paths through the Python error renderer.

## Idempotency

Create, PATCH, PUT and POST deletion accept an optional `Idempotency-Key` header:

- Accept exactly one opaque key of 1–128 printable ASCII characters, with no
  whitespace or comma. Invalid or duplicate header fields return 400.
- Scope keys by stable application/database namespace, public operation and route
  template, matching Express. Include item ID in the request fingerprint; the same
  key for a different item within the same operation conflicts rather than replaying
  another item's response. Different operations have separate replay scopes.
- Fingerprint normalized validated inputs, retaining the original `expected_version`
  on retries. The same key with changed input, or an in-progress claim, returns 409.
- Atomically retain the original successful status and JSON with the mutation.
  Replay those bytes/status without reapplying the operation or advancing its revision.
- Retain successful results for 24 hours from database completion. Replays do not
  extend retention. Replay remains valid after subsequent item changes or deletion.
- Do not cache failed attempts. Expired keys may execute again. Without a key,
  duplicate creation remains possible.
- Bound response storage and cleanup work using the Express policy as the reference.
  Cleanup is lifecycle-owned and must be safe across repeated/concurrent runs.

A response timeout does not cancel SQL or undo an already-started commit. A retry
using the same key reconciles an uncertain outcome once the durable result is
available. Idempotency keys do not provide authentication or authorization.

## Python implementation boundaries

Controllers declare the HTTP contract, assign awaited service results to named
variables, and validate response models before returning them. Services own the
operation rules; repositories handle SQL. The existing route owner retains the
transaction through service execution, controller validation and JSON preparation.

Identity/timestamp aliases and exact prices belong to the item-model alignment;
pagination defaults and sorting belong to collection alignment. Revision and
idempotency storage changes use explicit Alembic migrations. Existing ID width,
timestamp column mappings and decimal storage should be reused where compatible.
No production database transition is needed for this test application; migrations
and disposable MySQL evidence still establish reproducible setup.
