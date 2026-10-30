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

| Phase                                                     | Scope                                                                                                    | Completion check                                                                         |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **2A — Validated HTTP configuration (complete locally)**  | CORS, proxy trust, request budgets, and production defaults                                              | Invalid configuration fails startup; forwarding and browser preflight tests pass         |
| **2B — Operational endpoint exposure (complete locally)** | Configure documentation, diagnostics, and metrics availability; document unauthenticated access          | Enabled/disabled behavior matches policy; no implied protection from CORS or unused keys |
| **2C — Bounded rate limiting (complete locally)**         | Client-storage limits, quota/capacity responses, retry timing, expiry, and probe policy                  | Exhaustion and recovery tests pass; process-local limits are explicit                    |
| **2D — Logging and diagnostics (complete locally)**       | Safe error detail, consistent request outcomes, readable console output, deliberate production structure | Privacy, formatting, failure, timeout, and disconnect regression checks pass             |

### Milestone 3 — Migrations and production-like persistence

| Phase                                                       | Scope                                                                                                           | Completion check                                                                                                 |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **3A — Migration foundation (complete locally)**            | Alembic baseline for fresh databases; isolated disposable Docker development database; explicit schema creation | Explicit migrations create a fresh schema; startup rejects pending/incompatible revision history                 |
| **3B — Disposable MySQL testing (complete locally)**        | Guarded infrastructure; MySQL integration/E2E checks; safe setup/teardown                                       | Local checks passed; required-check configuration confirmed by the maintainer; hosted results tracked separately |
| **3C — Upgrade and rollback evidence (complete locally)**   | Real-baseline and test-only data-bearing migration qualification; defined history/drift checks and ordering     | MySQL evidence passes; future real migrations and historical image rollback require separate qualification       |
| **3D — Database capacity and transport (complete locally)** | Pool/queue bounds, acquisition/connect deadlines, TLS trust and identity                                        | Saturation, expiry/cancellation, socket cleanup, and verified TLS including native API/Alembic entrypoints pass  |
| **3E — Readiness and recovery (complete locally)**          | Bounded probes, outage/recovery behavior, stale connections, resource cleanup                                   | Local MySQL socket/HTTP checks pass on Windows and Linux; candidate hosted results remain separate               |

### Milestone 4 — Shutdown and mutation safety

| Phase                                                     | Scope                                                                                                                | Completion check                                                                                                                                  |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **4A — Graceful shutdown (complete locally)**             | Withdraw readiness, close admission, drain accepted work, clean dependencies, enforce final deadline                 | Windows/Linux process checks, real MySQL outcomes, and Docker SIGTERM smoke pass; hosted results remain separate                                  |
| **4B — Transaction ownership (complete locally)**         | One route-owned mutation transaction through service execution, controller model validation and response preparation | MySQL write/validation/rendering/pre-COMMIT failure, shared service/session ownership, and response-contract checks pass locally                  |
| **4C — Expiry and uncertain outcomes (complete locally)** | Shared monotonic activity checks, retained mutation ownership, broken-connection retirement, lost-response behavior  | Real HTTP/MySQL tests distinguish pre-commit rollback from commit uncertainty, lost acknowledgements and recovery; hosted results remain separate |

### Milestone 5 — Item API contract alignment (complete locally)

The [item specification](item-contract-specification.md) records the agreed Express
contract. All phases are implemented and verified with focused local checks; hosted
CI and release qualification remain separate.

| Phase                                                             | Scope                                                                                                                             | Completion check                                                                                                                                  |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **5A — Compatibility decisions (complete locally)**               | Express IDs, timestamp/sort names, page defaults, price rules, deletion route, versions and retry contract                        | Item specification accepted; runtime implementation remains tracked below                                                                         |
| **5B — Item models, exact prices and filters (complete locally)** | Alphanumeric IDs, response timestamp aliases, Decimal precision/range, accepted inputs, response validation and inclusive filters | Identity/model and price-boundary tests pass; rejected mutations leave MySQL unchanged; hosted CI remains separate                                |
| **5C — Deterministic pagination (complete locally)**              | Unique sorting tie-breaker, safe offsets, agreed query names/defaults, repeated/crossed query validation                          | Equal-sort-value pages are deterministic for unchanged data; pagination limits are documented                                                     |
| **5D — Optimistic concurrency (complete locally)**                | Revision migration/backfill, required `expected_version`, stale-write protection and agreed deletion route                        | Focused Windows concurrency, missing/stale versions, overflow, rollback and migration checks passed; hosted CI remains separate                   |
| **5E — Durable idempotency (complete locally)**                   | Optional keys, fingerprinting, atomic replay, conflicts, retention, bounded cleanup                                               | MySQL/HTTP replay, rollback, expiry and cleanup checks passed; fixed fingerprint vectors and supported-input registration guards verified locally |

### Milestone 6 — Production container and CI enforcement (complete)

| Phase                                                     | Scope                                                                                                               | Completion check                                                                                                                                        |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **6A — Runtime hardening (complete locally)**             | Non-root user, runtime-only dependencies, digest-pinned bases and update process                                    | Focused Windows checks passed; maintainer confirmed hosted CI passed on 2026-10-30                                                                      |
| **6B — MySQL container qualification (complete locally)** | Extend built-image MySQL CRUD/probe/shutdown qualification with restart and persistence evidence                    | Qualification step passed in hosted run 41089796696; subsequent security changes require candidate requalification                                      |
| **6C — Dependency and image security (complete locally)** | Runtime/full Python audits and exact qualified-image scan; critical-only blocking, warnings and expiring exceptions | Dependency audit, qualified-image scan and report uploads passed in run 41096725174                                                                     |
| **6D — Aggregate CI gate (complete locally)**             | Retain reports/logs; always-running final job; verify workflow triggers                                             | All required jobs, Deployment gate and evidence uploads passed in run 41096725174; 51 offline gate/workflow tests passed                                |
| **6E — Required branch checks (complete locally)**        | Run hosted CI, confirm exact check/source names, configure rulesets                                                 | Active main/dev/staging ruleset requires only Deployment gate from GitHub Actions (15368); individual requirements removed and other settings preserved |

### Milestone 7 — Verified release pipeline

| Step | Scope | Completion check |
| --- | --- | --- |
| **7A–7C — Verified candidate publication (complete; hosted publication passed)** | Exact-source main CI; one OCI candidate with SBOM/provenance; MySQL/security qualification; disposable registry rehearsal; digest-preserving publication and retained evidence | Release run 41129765731 passed build, qualification, registry rehearsal and real publication |
| **7D — Release rollback procedure (implemented; retained-image exercise pending)** | Retained image selection, exact schema compatibility, current → rollback → current and release ordering | 23 offline Windows checks passed; manual disposable workflow/runbook implemented; actual historical pair requires two compatible published releases |

### Milestone 8 — Hosting-dependent verification (deferred)

Retained here as deferred backlog. It is outside the current delivery scope and
will be reconsidered when hosting is selected.

- **8A — Ingress and access:** real proxy/client-IP trust, browser CORS, authorized operational access, direct-port denial, and server/ingress header-receive and whole-upload deadlines. Qualify slow/incomplete headers and stalled/trickled uploads over real connections, including prevention of direct-port bypass; application response/body-read deadlines and keep-alive settings do not establish these guarantees. See [the transport boundary](request-timeouts.md#server-and-ingress-boundary).
- **8B — Platform lifecycle:** traffic withdrawal, termination grace, database outages, and failover/recovery.
- **8C — Database operations:** deployment CA/DNS, certificate rotation, fleet connection capacity, durable storage, backups, and restore exercises.
- **8D — Observability:** log access/retention, dashboards, alerting, and deployment diagnostics.

Full authentication/authorization remains a separate scope decision. Shared Redis rate limiting remains deferred until deployment-wide enforcement is needed.

Each phase includes implementation, relevant tests, documentation, and recorded evidence. Reassess estimates when dependency or environment constraints change.
Update its completion status here when finishing the work, alongside the verification record.

## Planning and verification boundaries

This is the single source of truth for implementation scope, status and deferred
work. Reference guides describe supported behavior; [Verification](verification.md)
records dated execution evidence.

- Express defines the agreed item contract; use native Python mechanisms and retain controller response validation and service ownership.
- Use pip with manually maintained requirements. Runtime and development dependencies remain separate.
- Local verification uses focused Windows tests and relevant static checks. Run the full Windows suite only when scope warrants it; leave Linux, TLS and production-image qualification to CI. Repeat checks only when changes or failures justify it.
- Application HTTP settings do not establish slow-header or whole-upload transport protection. Server/ingress configuration and deployed checks remain under 8A.
- Every future schema change needs representative-data upgrade and supported rollback evidence. Migration rollback does not establish backup restoration; image rollback requires schema compatibility.
- Authentication/authorization remain outside the small items API's scope. CORS and unused keys provide no authentication. Shared Redis rate limiting is deferred until deployment-wide enforcement is needed.
- Hosted execution and the saved required-check ruleset were verified on 2026-10-30: main/dev/staging require Deployment gate from GitHub Actions. Administrator bypass remains explicitly configured.

Keep passed, failed, skipped, not-run and unavailable evidence distinct. Local
coverage or workflow definitions alone do not establish a verified release.
