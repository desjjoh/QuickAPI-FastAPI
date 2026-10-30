# Express parity roadmap

[Documentation index](../README.md#documentation)

The [milestone and phase list](milestones.md) defines implementation order and
acceptance criteria. [Backlog](backlog.md) tracks unresolved requirements, and
[Verification](verification.md) records dated execution evidence. Reference guides
describe the supported application contracts.

| Milestone | Focus                                            |
| --------- | ------------------------------------------------ |
| 1         | Reproducible foundation and existing fixes       |
| 2         | HTTP policies and operational behavior           |
| 3         | Migrations and production-like MySQL persistence |
| 4         | Shutdown and mutation safety                     |
| 5         | Item API contract alignment                      |
| 6         | Production container and CI enforcement          |
| 7         | Verified release pipeline                        |
| 8         | Hosting-dependent verification                   |

## 1A. Environment and dependencies

The project targets Python 3.12 and uses pip with manually pinned runtime/development
requirements. Development and CI install the development requirements; the runtime
image contains runtime dependencies. See [Development](development.md) for setup and
[Verification](verification.md) for execution evidence.

## 1B. Startup and branch protections

Local Compose supplies MySQL, authenticated health-based startup ordering, persistent
project-scoped storage, and loopback-only publishing. Required hosted-check contexts
and the remote ruleset verification procedure are documented in
[Branch protections](branch-protection.md#required-check-configuration). Local startup
and persistence checks do not establish remote check enforcement.

## 1C. Request timeout correctness

The [request deadline contract](request-timeouts.md) defines pre-header JSON 408s,
stream interruption, disconnect/cancellation handling, and cleanup boundaries.
Database transaction and application-wide shutdown guarantees have separate acceptance
criteria in the milestone list.

## 1D. Metrics and request outcomes

Logging and metrics share one response outcome/duration. Completed responses and
aborts are counted separately; route and method labels are bounded. See
[the metrics contract](deployment.md#metrics-and-request-outcomes) and
[regression coverage](testing.md#request-outcome-regression-coverage).

## 2A. Validated HTTP configuration

[HTTP configuration](http-policy.md) defines Pydantic Settings defaults and optional
env overrides for CORS, proxy IP/CIDR trust, request deadlines, size budgets, and
method/media policies. Slow-header and whole-upload receive protection requires a
supported server/ingress configuration and deployed verification.

## 2B. Operational endpoint exposure

[Operational exposure](operational-exposure.md) defines docs/diagnostics/metrics flags,
production defaults, and disabled-path behavior. Public readiness omits dependency
details; metric collection is independent of HTTP exposition. Enabled operational
endpoints require the consuming deployment's access restrictions.

## 2C. Bounded rate limiting

[Rate limiting](rate-limiting.md) defines exact rolling windows, request/client/storage
bounds, 429/503 responses, retry timing, and per-process enforcement. Probes/preflights
share quota, favicon GET/HEAD is exempt, and the guide documents the CORS boundary.

## 2D. Logging and diagnostics

[Logging](logging.md) defines console/production JSON output, native severity levels,
successful-request DEBUG records, safe error diagnostics, configuration privacy, and
standard/dependency logging controls. [Verification](verification.md) identifies the
validated source snapshot and execution boundaries. Deployment log access, retention,
and shipping require hosting-specific controls.

## 3A. Migration foundation

[Alembic migrations](migrations.md) define the fresh schema and explicit native/container commands. The isolated `quickapi-fastapi-dev` Compose project publishes MySQL on loopback port 3310. Startup checks revision compatibility without creating tables; deeper drift/data compatibility and hosted CI qualification remain separate requirements. Development data is disposable, with an intentional project-scoped reset.

## 3B. Disposable MySQL testing

[MySQL testing](mysql-testing.md) defines the separate temporary test stack, explicit `.env.test` connection, guarded migrations/resets, real-commit persistence fixtures, serial execution, and integration/E2E CI jobs. MySQL is the only persistence backend for tests and combined coverage. Hosted check execution/enforcement requires independent verification.

## 3C. Upgrade and rollback evidence

[Migration qualification](migrations.md#upgrade-and-rollback-qualification) covers the real baseline and an isolated test-only additive/backfill chain. Data preservation, defaults/indexes, reversible schema changes, partial MySQL DDL failure, history rejection, and defined drift cases have executable checks. Startup retains strict revision equality, so deployment ordering is stopped-application migration followed by the matching application. Future real migrations require their own data/compatibility evidence; historical image rollback and backup restoration are separate requirements.

## 3D. Database capacity and transport

[Database settings](database-settings.md) defines shared engine limits, bounded caller admission, separate acquisition/connection deadlines, and verified TLS. Tests cover saturation, cancellation, disposal/invalidation, socket cleanup, certificate rejection, and native TLS startup. Existing MySQL integration CI includes independent TLS qualification. [Readiness and recovery](database-lifecycle.md) defines bounded shared probes, startup cleanup, and runtime outage recovery. Hosting-specific CA/fleet behavior remains a separate acceptance criterion.

## 3E. Readiness and recovery

[Database lifecycle](database-lifecycle.md) defines bounded shared probes, short
success/failure caching, independent liveness, startup verification cleanup, and
connection retirement. MySQL socket tests exercise repeated outages, stalled
responses, stale sessions, acquisition exhaustion, and recovery on the same API.
Full traffic withdrawal and request draining remain shutdown requirements.

## 4B. Transaction ownership

[Mutation transactions](transactions.md) keeps one request-owned transaction around
service/repository work and native FastAPI response preparation. Repositories
participate through the supplied session, without independent commits. Controllers
delegate to services that own application logic, then validate returned results
into response models before returning them.

## 4C. Expiry and uncertain outcomes

[Mutation transactions](transactions.md#expiry-and-commit-outcomes) defines shared
monotonic activity checks before work, after acquisition, and immediately before
commit. HTTP timeout/disconnect retains the mutation task through settlement and
cleanup, while suppressing late output. Real MySQL packet barriers and HTTP socket
tests distinguish pre-commit rollback, commit acknowledgement loss, cancellation,
post-commit failure, invalidation and recovery. No SQL-cancellation or retry-safety
guarantee is implied; durable idempotency remains a separate contract.

## Working decisions

[Graceful shutdown](shutdown.md) defines early readiness withdrawal, closed HTTP
admission, accepted-work draining, reverse dependency cleanup, and final process
termination. The supported entrypoint coordinates Uvicorn and development reload;
transaction ownership and request activity share that accepted-work lifetime.

- Use Express and NestJS as references for behavior and quality. Prefer native FastAPI/Pydantic/SQLAlchemy/Uvicorn mechanisms where they satisfy the same requirements.
- Use pip with manually maintained requirements; no uv adoption or generated lockfile is planned.
- Review concrete public-contract changes before milestone 5: IDs, names, defaults, price acceptance, required revisions, deletion route, and replay headers.
- Tests and documentation land with each phase. Record passed, failed, skipped/not run, and unavailable checks separately; require exact-source hosted evidence before claiming a release.
- Local MySQL coverage and image checks do not establish deployed production readiness; verification claims require evidence for the relevant environment and source.

## Scope and operational boundaries

Authentication/authorization remain a separate scope decision; operational endpoint exposure is included in 2B. CORS and an unconsumed metrics key are not authentication. Shared Redis limiting is deferred until multi-instance enforcement is needed.

Migration upgrades, representative backfills, and supported rollback evidence are repository/CI work. Real ingress/access rules, orchestrator behavior, deployed CA/DNS/rotation, fleet capacity, log retention, durable storage, and backup restoration require the chosen hosting environment and remain in milestone 8. A down migration or retained image does not prove backup restoration or schema-compatible rollback.

Estimates do not replace acceptance criteria. Reassess scheduling when database or environment constraints change. Remove resolved items from the backlog, document supported behavior in reference guides, and record execution evidence in Verification.
