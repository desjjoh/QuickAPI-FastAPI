# Express parity roadmap

[Documentation index](../README.md#documentation)

The agreed [milestone and phase list](milestones.md) is the source of truth for implementation order and testable completion conditions. It expands the earlier four-milestone outline into eight milestones. [Backlog](backlog.md) tracks remaining work using those current phase numbers; [Verification](verification.md) records completed behavior and check results.

| Milestone | Focus |
| --- | --- |
| 1 | Reproducible foundation and existing fixes |
| 2 | HTTP policies and operational behavior |
| 3 | Migrations and production-like MySQL persistence |
| 4 | Shutdown and mutation safety |
| 5 | Item API contract alignment |
| 6 | Production container and CI enforcement |
| 7 | Verified release pipeline |
| 8 | Hosting-dependent verification |

## 1A. Environment and dependencies

Completed locally with pip, manually pinned runtime/development requirements, and a Python 3.12 project environment. Fresh Windows/Linux installations, static checks, the complete suites, Linux critical coverage gates, runtime dependency exclusion, and the existing SQLite image smoke passed. See [the verification record](verification.md) for versions, working-tree/image identity, results, and limitations. Hosted CI for that working tree remains unverified; see 1B for subsequent Compose/rule inventory evidence.

## 1B. Startup and branch protections

Local Compose now supplies MySQL, authenticated health-based startup ordering, consistent container settings/ports, and persistent project-scoped storage. A fresh disposable project passed readiness, item create/read, and persistence across container recreation. The workflow adds major-branch pushes, merge groups, and manual dispatch while preserving current check names. See [Verification](verification.md).

Live FastAPI structural protections match Express. Six existing hosted checks were confirmed from a successful historical run, but FastAPI's required-check list is empty. This phase remains **partially complete** until the [manual required-check setting](branch-protection.md#remaining-manual-setting) is saved and verified. No hosted result for this working tree or remote rule update is claimed.

## 1C. Request timeout correctness

Completed ahead of order and retained intentionally. The remaining 1B required-check configuration is still pending; 1D is now complete locally; see the [backlog sequence note](backlog.md#sequence-note--timeout-work-completed-ahead-of-order).

The Express-aligned timeout/streaming/disconnect contract is implemented and verified locally. See [Request deadlines](request-timeouts.md) for behavior and cancellation limits, and [Verification](verification.md) for execution evidence. This is the timeout phase called 1B in the earlier four-milestone outline; expanded phase 1B (Compose/branch settings) remains pending.

## 1D. Metrics and request outcomes

Completed locally. Logging and metrics now share one response outcome and duration;
completed responses and aborts are counted separately, and route/method labels stay
bounded. Names, labels, units, and histogram buckets match the Express/NestJS
contract while preserving Python log levels and the current error envelope. See
[the metrics contract and dashboard migration](deployment.md#metrics-and-request-outcomes),
[regression coverage](testing.md#request-outcome-regression-coverage), and
[Verification](verification.md). Remaining phase 1B branch-check configuration is
still a separate manual step; broader logging work remains phase 2D.

## 2A. Validated HTTP configuration

Application configuration is implemented locally with defaults in Pydantic Settings
and optional env overrides. Exact CORS origins, proxy IP/CIDR trust, request deadlines,
size budgets, and method/media policies are validated and wired into the stack.
[HTTP configuration](http-policy.md) documents ranges, source precedence, behavior
changes, and external-server requirements. True slow-header/whole-upload receive
protection remains an explicit deployment task; phase 2A does not claim that the
application deadlines provide it. See [Verification](verification.md).

## Working decisions

- Use Express and NestJS as references for behavior and quality. Prefer native FastAPI/Pydantic/SQLAlchemy/Uvicorn mechanisms where they satisfy the same requirements.
- Use pip with manually maintained requirements; no uv adoption or generated lockfile is planned.
- Review concrete public-contract changes before milestone 5: IDs, names, defaults, price acceptance, required revisions, deletion route, and replay headers.
- Tests and documentation land with each phase. Record passed, failed, skipped/not run, and unavailable checks separately; require exact-source hosted evidence before claiming a release.
- The supplied A-range application/B+ production-assurance assessment is the planning baseline, not a newly verified grade. SQLite coverage and a local smoke do not establish MySQL or production readiness.
- The earlier Python 3.14-only execution limitation was an environment mismatch, not a test failure. Phase 1A now supplies a verified 3.12 path without retargeting application code.

## Scope and operational boundaries

Authentication/authorization remain a separate scope decision; operational endpoint exposure is included in 2B. CORS and an unconsumed metrics key are not authentication. Shared Redis limiting is deferred until multi-instance enforcement is needed.

Migration upgrades, representative backfills, and supported rollback evidence are repository/CI work. Real ingress/access rules, orchestrator behavior, deployed CA/DNS/rotation, fleet capacity, log retention, durable storage, and backup restoration require the chosen hosting environment and remain in milestone 8. A down migration or retained image does not prove backup restoration or schema-compatible rollback.

The two-to-three-day estimate is a working estimate, not permission to omit verification. Reassess after baseline and MySQL/migration work expose actual constraints. Remove completed items from the backlog and retain their evidence in implementation guides and verification records.
