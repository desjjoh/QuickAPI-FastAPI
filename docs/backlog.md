# Technical backlog

[Documentation index](../README.md#documentation)

These items describe the checked-in implementation, not completed work or release evidence. Reverify against the current checkout before implementation and update this list when behavior changes.

## Confirmed gaps

| Area | Current gap | Completion evidence |
| --- | --- | --- |
| Compose | Required `APP_VERSION`, `ENV`, and `PORT` are absent; `DEBUG`/`WORKERS` are unused | Validated settings and Compose readiness/API smoke checks |
| Dependencies | Development manifest conflicts with main pytest/pytest-asyncio pins; runtime image includes quality tools | Resolve duplicate pins, define runtime/dev split, verify fresh installs and container checks |
| Streaming timeout | Middleware may render a second response after HTTP headers started | Response-state handling and timeout regression coverage before/after response start |
| Metrics | Raw URL paths create series for individual IDs and unknown routes | Route-template labels and bounded unmatched-route coverage |
| Price | Float validation does not match database `Numeric(10, 2)` precision/range | Decide rounding/rejection policy and verify models/storage on the target engine |
| Pagination | Sorting lacks a unique tie-breaker | Defined stable ordering and tests with equal sort values |

## Deferred capabilities

- Authentication/authorization and operational access: select and implement the consuming service's trust boundary. CORS and an unconsumed metrics key provide no authentication.
- Migrations and MySQL verification: reviewed revisions and target-engine checks are needed before claiming deployed-schema safety.
- Shared rate-limit storage: current limits are process-local and cover probes too; decide global and operational policies before scaling.
- Mutation concurrency/idempotency: define contracts and uncertain-outcome handling before introducing retries.
- Release operations: immutable promotion, durable storage, backups/restores, compatible rollback, and environment-specific validation remain operator responsibilities.

## Documentation maintenance

Keep README as the entry point and detailed guidance in this directory, matching sibling QuickAPI/QuickFE repos. Link implementation/configuration sources, document runnable commands and limits, and distinguish configured gates from verified results. Update guides with behavior changes; avoid copying unrelated features or readiness claims from other apps.
