# Technical backlog

[Documentation index](../README.md#documentation)

The [roadmap](roadmap.md) and [milestone list](milestones.md) define implementation
order and acceptance criteria. This backlog contains unresolved requirements using
their phase identifiers. Dated results belong to [Verification](verification.md);
reference guides describe supported behavior.

## Branch-check enforcement

Save and verify the six required GitHub checks according to
[the configuration guide](branch-protection.md#required-check-configuration).
Repository workflow definitions and local runtime checks do not establish that a
remote ruleset enforces those contexts for a candidate pull request.

## Foundation and server work

| Remaining work | Roadmap phase |
| --- | --- |
| Save and verify the six confirmed required checks in GitHub; structural rules/check inventory already verified | 1B, 6E |
| True server/ingress header/whole-upload receive protection and deployed proxy/direct-port verification; application HTTP configuration is implemented locally | 2A deployment boundary, 8 |
| Alembic baseline, explicit migrations, pending/history/drift checks | 3A, 3C |
| Guarded disposable MySQL integration/E2E infrastructure and required CI checks | 3B |
| Representative-data upgrades/backfills and supported migration/application rollback evidence | 3C and every later schema change |
| Pool/queue capacity, acquisition/connect budgets, TLS policy, readiness outage/recovery | 3D, 3E |
| Shutdown admission, drain, cleanup, and final deadline | 4A |

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
