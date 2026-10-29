# Implementation milestones

## Summary

This plan defines implementation scope and acceptance criteria. Completion status
is limited to the evidence in [Verification](verification.md). Hosted CI, remote
branch enforcement, and deployed guarantees require independent verification.

### Milestone 1 — Reproducible foundation and existing fixes

Required-check enforcement is tracked under 1B/6E. See
[Branch protections](branch-protection.md#required-check-configuration) for setup
and verification requirements.

| Phase                                                      | Scope                                                                                                    | Completion check                                                                                                         |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **1A — Environment and dependencies (complete locally)**   | Establish Python 3.12 execution; resolve conflicting pins; separate runtime and development requirements | Fresh installations and static/test checks run reproducibly; environment limitations recorded separately                 |
| **1B — Startup and branch protections (complete locally)** | Fix Compose configuration; verify ruleset targets, protections, and available check names                | Compose reaches readiness and serves an API request; protection settings documented without requiring nonexistent checks |
| **1C — Request timeout correctness (complete locally)**    | Handle response-start state, streaming expiry, disconnects, cleanup, and late responses                  | No duplicate headers or late responses; focused ASGI and real-server checks pass                                         |
| **1D — Metrics and request outcomes (complete locally)**   | Bound route labels; consistently record completion, failure, timeout, and abort                          | Varying IDs/unknown URLs cannot grow metric labels without bound; outcome tests pass                                     |

### Milestone 2 — HTTP policies and operational behavior

| Phase                                                                                           | Scope                                                                                                    | Completion check                                                                         |
| ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **2A — Validated HTTP configuration (application complete locally; transport protection open)** | CORS, proxy trust, request budgets, and production defaults                                              | Invalid configuration fails startup; forwarding and browser preflight tests pass         |
| **2B — Operational endpoint exposure (complete locally)**                                       | Configure documentation, diagnostics, and metrics availability; document unauthenticated access          | Enabled/disabled behavior matches policy; no implied protection from CORS or unused keys |
| **2C — Bounded rate limiting (complete locally)**                                               | Client-storage limits, quota/capacity responses, retry timing, expiry, and probe policy                  | Exhaustion and recovery tests pass; process-local limits are explicit                    |
| **2D — Logging and diagnostics (complete locally)**                                             | Safe error detail, consistent request outcomes, readable console output, deliberate production structure | Privacy, formatting, failure, timeout, and disconnect regression checks pass             |

### Milestone 3 — Migrations and production-like persistence

| Phase                                                | Scope                                                                                                           | Completion check                                                                                                 |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **3A — Migration foundation (complete locally)**     | Alembic baseline for fresh databases; isolated disposable Docker development database; explicit schema creation | Explicit migrations create a fresh schema; startup rejects pending/incompatible revision history                 |
| **3B — Disposable MySQL testing (complete locally)** | Guarded infrastructure; MySQL integration/E2E checks; safe setup/teardown                                       | Local checks passed; required-check configuration confirmed by the maintainer; hosted results tracked separately |
| **3C — Upgrade and rollback evidence**               | Representative existing rows, backfills, defaults, indexes, migration history/drift, deployment ordering        | Upgrade preserves intended data; supported downgrade/application rollback is exercised and documented            |
| **3D — Database capacity and transport**             | Pool/queue bounds, acquisition/connect deadlines, TLS trust and identity                                        | Saturation, expired acquisition, handshake, and TLS acceptance/rejection tests pass                              |
| **3E — Readiness and recovery**                      | Bounded probes, outage/recovery behavior, stale connections, resource cleanup                                   | MySQL failure/recovery tests demonstrate correct readiness and connection lifecycle                              |

### Milestone 4 — Shutdown and mutation safety

| Phase                                  | Scope                                                                                                | Completion check                                                                                                             |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **4A — Graceful shutdown**             | Withdraw readiness, close admission, drain accepted work, clean dependencies, enforce final deadline | Process tests cover idle shutdown, active mutations, disconnects, and stuck work                                             |
| **4B — Transaction ownership**         | One mutation transaction covering persistence and response preparation before commit                 | Write, validation, serialization, and commit failures produce the documented rollback behavior                               |
| **4C — Expiry and uncertain outcomes** | Pre-commit activity checks, cancellation handling, session reuse, lost-response behavior             | Tests distinguish rollback before commit from uncertain outcomes during/after commit; no unsupported SQL-cancellation claims |

### Milestone 5 — Item API contract alignment

Review the concrete client-facing changes before implementing this milestone.

| Phase                             | Scope                                                                                              | Completion check                                                                                                |
| --------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **5A — Compatibility decisions**  | IDs, timestamp/sort names, page defaults, price rules, deletion route, versions, and retry headers | Agreed before/after contract and migration implications                                                         |
| **5B — Exact prices and filters** | Decimal precision/range, accepted inputs, response validation, inclusive price filters             | Boundary/malformed/excess-precision tests pass; rejected mutations leave MySQL unchanged                        |
| **5C — Deterministic pagination** | Unique sorting tie-breaker, safe offsets, repeated/crossed query validation                        | Equal-sort-value pages are deterministic for unchanged data; pagination limits are documented                   |
| **5D — Optimistic concurrency**   | Revision migration/backfill, required `expected_version`, stale-write/delete protection            | Concurrent writes, missing rows, overflow, rollback, and upgrade compatibility tests pass                       |
| **5E — Durable idempotency**      | Optional keys, fingerprinting, atomic replay, conflicts, retention, bounded cleanup                | MySQL/HTTP tests cover duplicate concurrency, replay, failure rollback, expiry, cleanup, and later item changes |

### Milestone 6 — Production container and CI enforcement

| Phase                                  | Scope                                                                                 | Completion check                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **6A — Runtime hardening**             | Non-root user, runtime-only dependencies, digest-pinned bases and update process      | Actual image identity, permissions, dependency contents, and startup are verified                   |
| **6B — MySQL container qualification** | Replace SQLite-only qualification with explicit migrations and disposable MySQL       | Built-image CRUD, probes, static assets, exposure, restart/persistence, and termination checks pass |
| **6C — Dependency and image security** | Dependency audit, exact final-image scan, blocking policy, scoped expiring exceptions | Scanner/policy failures block; unrelated findings cannot be hidden by exceptions                    |
| **6D — Aggregate CI gate**             | Retain reports/logs; always-running final job; verify workflow triggers               | Required failed, cancelled, missing, or skipped jobs cannot yield a passing gate                    |
| **6E — Required branch checks**        | Run hosted CI, confirm exact check/source names, configure rulesets                   | An ordinary PR requires the real gate and cannot merge around failed checks                         |

### Milestone 7 — Verified release pipeline

| Phase                                        | Scope                                                                                   | Completion check                                                                          |
| -------------------------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **7A — Candidate identity and attestations** | Exact-source CI requirement; build one candidate with SBOM/provenance                   | Source, image, and attestations are bound and validated                                   |
| **7B — Candidate qualification**             | MySQL smoke and security scan of that same candidate; retained evidence                 | Failed candidates or mismatched/incomplete evidence cannot publish                        |
| **7C — Digest-preserving publication**       | Publish without rebuilding; retain commit/digest identity; exercise dry-run/publication | Published digest matches the verified candidate                                           |
| **7D — Release rollback procedure**          | Retained image selection, schema compatibility, release ordering                        | Supported rollback procedure is documented and exercised within disposable infrastructure |

### Milestone 8 — Hosting-dependent verification

Tracked now, executed when hosting is selected.

- **8A — Ingress and access:** real proxy/client-IP trust, browser CORS, authorized operational access, and direct-port denial.
- **8B — Platform lifecycle:** traffic withdrawal, termination grace, database outages, and failover/recovery.
- **8C — Database operations:** deployment CA/DNS, certificate rotation, fleet connection capacity, durable storage, backups, and restore exercises.
- **8D — Observability:** log access/retention, dashboards, alerting, and deployment diagnostics.

Full authentication/authorization remains a separate scope decision. Shared Redis rate limiting remains deferred until deployment-wide enforcement is needed.

Each phase includes implementation, relevant tests, documentation, and recorded evidence. Reassess estimates when dependency or environment constraints change.
