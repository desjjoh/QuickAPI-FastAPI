# Technical backlog

[Documentation index](../README.md#documentation)

The [Express parity roadmap](roadmap.md) defines the agreed sequence, scope, and testable completion conditions. Phases 1A, 1C, and 1D are complete locally; see [Verification](verification.md). Entries below are remaining work, using the expanded phase numbers in [Milestones](milestones.md). Reverify current source before implementation. Remove completed entries and record behavior/evidence in the relevant guide or CI record.

## Sequence note — timeout work completed ahead of order

Phase **1C — Request timeout correctness** was completed ahead of **1B — Startup and branch protections** after using the timeout phase's number from the earlier outline. Keep the implemented changes; no rollback is planned.

The completed work covers response-state tracking, one pre-header JSON 408, interrupted streams without replacement responses, disconnect/cancellation handling, bounded body-message ownership, tracked cleanup/late failures, and the `first_body_timeout` rename. Real Uvicorn socket checks and the follow-up Pylance typing fixes are recorded in [Verification](verification.md); behavior and limitations live in [Request deadlines](request-timeouts.md).

**Remaining phase 1B work: save and verify required status checks.** Compose startup/MySQL persistence are verified locally, the structural rules match Express, and existing hosted check names are confirmed. Adding those six checks still requires the [manual GitHub setting](branch-protection.md#remaining-manual-setting). Phase 1D is now complete locally; continue with milestone 2 after the remaining setting is verified. Do not repeat 1C. Database rollback, running-SQL cancellation, and application shutdown draining remain in their later phases.

## Foundation and server work

| Remaining work | Roadmap phase |
| --- | --- |
| Save and verify the six confirmed required checks in GitHub; structural rules/check inventory already verified | 1B, 6E |
| Validated CORS/proxy trust, HTTP budgets (including true server/ingress header-receive protection), and operational/docs/metrics exposure | 2A, 2B |
| Bounded rate-limit storage, capacity/quota responses, retry timing, probe policy | 2C |
| Alembic baseline, explicit migrations, pending/history/drift checks | 3A, 3C |
| Guarded disposable MySQL integration/E2E infrastructure and required CI checks | 3B |
| Representative-data upgrades/backfills and supported migration/application rollback evidence | 3C and every later schema change |
| Pool/queue capacity, acquisition/connect budgets, TLS policy, readiness outage/recovery | 3D, 3E |
| Safe logging/diagnostics (including third-party debug output at ERROR); shutdown admission, drain, cleanup, final deadline | 2D, 4A |

## Item contracts and persistence

| Remaining work | Roadmap phase |
| --- | --- |
| Transaction ownership through response preparation; pre-commit expiry handling and uncertain commit outcomes | 4B, 4C |
| Decimal price validation aligned with storage; matching filter rules | 5A, 5B |
| Unique pagination tie-breaker, safe offsets, explicit defaults/naming/ID compatibility decisions | 5A, 5C |
| Revision migration/backfill, required preconditions, stale-write protection, agreed deletion route | 5D |
| Atomic durable idempotency, replay conflicts, retention, bounded cleanup, failure/retry evidence | 5E |

## Production assurance and release enforcement

| Remaining work | Roadmap phase |
| --- | --- |
| Non-root runtime and digest-pinned bases; runtime/dev dependency separation verified in 1A | 6A |
| Actual production-container smoke against MySQL instead of SQLite, including mutations and lifecycle | 6B |
| Dependency audit and exact final-image scan, blocking policy, scoped expiring exceptions | 6C |
| Retained results/security evidence and an always-running aggregate fail-closed CI job | 6D |
| Configure/verify required GitHub status checks once those checks actually run | 6E |
| SBOM/provenance, exact-source release gate, MySQL candidate verification, digest-preserving publication and rollback identity | 7A–7D |

## Explicit scope and deferred deployment work

- Authentication/authorization remain outside the deliberately small items API's scope, matching Express. This is an access limitation to document, not an implicit commitment to build an identity system. Operational exposure policy is included in 2B; CORS and an unconsumed metrics key provide no authentication.
- Shared Redis rate limiting remains deferred until multi-instance enforcement is needed. Current enforcement is process-local.
- Real ingress/proxy trust, authorized diagnostic access/direct-port denial, orchestrator drain/failover, deployment CA/DNS/rotation, fleet connection capacity, log retention, durable storage, and backup restoration need the selected hosting environment. See [Deployment](deployment.md).
- Migration rollback tests do not establish backup restoration. Image rollback requires schema compatibility. These boundaries remain explicit even after repository gates pass.

## Verification discipline

The supplied assessment is A-range application code/testing discipline and B+ production assurance; it is not a fresh verification of this commit. The roadmap closes the listed assurance gaps and records environment-dependent evidence separately. Keep passed, failed, skipped/not run, and unavailable results distinct. Defined workflows, test counts, or SQLite coverage alone do not establish a verified MySQL release.
