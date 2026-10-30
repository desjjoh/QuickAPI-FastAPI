# Verification report

[Documentation index](../README.md#documentation)

## Source and environment

Verified on 2026-10-29 against base commit
`802af92d5a77267dfff0baf60df7ad8aaad920da` and the local fingerprints below.
The candidate includes uncommitted changes; the base commit alone does not identify
it. This report describes the current MySQL-only application and tests. Earlier
verification snapshots remain in Git history and do not define current support.

Windows uses Python 3.12.10. Linux uses Python 3.12.16 with disposable dependencies
and read-only source mounts. Persistence tests use guarded disposable MySQL 8.4.6.
The development database is separate and was not modified.

## Results

| Check | Result |
| --- | --- |
| Windows full MySQL suite | 989 passed; two POSIX-only cases skipped; five dedicated TLS cases deselected; 95.77% branch-measured application coverage |
| Linux full MySQL suite | 991 passed; no skips; five dedicated TLS cases deselected; 95.86% branch-measured application coverage |
| Database-independent units | 641 passed with an unreachable configured database target; no database-backed fixtures selected |
| Dedicated TLS | Five cases passed on Windows against the separate generated-certificate MySQL server |
| Coverage gates | Middleware 97%, lifecycle 99%, database package 95%, API 99%; all configured gates passed on both platforms |
| Formatting/linting | Black: 165 files unchanged; Ruff passed |
| Type checking | mypy: 68 application/tool files passed; strict Pyright: 5 affected files, zero diagnostics, using explicit installed typeshed |
| Dependencies | Local and fresh-image pip checks passed; removed optional database driver absent from both; pytest absent from runtime image |
| Transaction HTTP qualification | Existing 32-case preparation/ownership module passes in both full suites; 21 additional real HTTP/MySQL expiry and uncertainty cases pass in both suites |
| Expiry and uncertain outcomes | Monotonic checks, expired acquisition without business SQL, caught cancellation, all four mutation methods after writes, real disconnects, held INSERT results, interrupted COMMIT, lost acknowledgement, confirmed commit before lost response, cleanup failure, invalidation and recovery |
| Transaction ownership | Four marked item mutation routes share one explicit request session; repositories never commit/roll back independently; read routes remain unmarked |
| Boundary guards | Existing owner/active factory session rejected; shared dependencies borrow without closing; completed owner cannot silently autobegin; streams/background tasks rejected and prepared error responses rolled back |
| Configuration | Only mysql+asyncmy accepted; test configuration remains independent of development .env |
| Migration behavior | Empty-schema rejection, baseline/model comparison, repeated upgrade, incompatible history, downgrade/reapply, offline SQL and real online commands pass against MySQL |
| Pool/session cleanup | Real MySQL late-connection disposal, queue/cancellation/invalidation, and server-session disappearance checks pass |
| Safety | Live identity checks, exclusive reset guards, destructive schema restoration, unavailable-target failure, and isolated command-lock tests pass |
| CI definition | Unit job, MySQL integration/E2E, full MySQL coverage, dedicated TLS and independent MySQL image qualification; YAML parses |
| Image-runner failures | Database startup, HTTP-check, and artifact-write failures all attempt disposable-project teardown |
| Built runtime image | sha256:a4822d3610451ecb9339ff7a2a34f12e9902e8890e7e94610105a84ff63e0797 |
| Built-image MySQL qualification | Explicit migration, CRUD, probes, favicon, production exposure defaults, pip check, Docker SIGTERM, exit zero and final success record passed |
| Cleanup | Generated TLS material, independent smoke/TLS projects and verification containers removed; existing development/regular test services retained |
| Hosted CI / branch enforcement | Not run / not independently verified for this candidate |

## Boundaries

All persistence fixtures use MySQL. No other database backend is selected or used
as a fallback. Unit tests use test doubles and do not require Docker. Direct full
pytest requires the disposable server to be started and migrated; the wrapper
manages that lifecycle and measures coverage. Dedicated TLS cases remain explicit
qualification with their own temporary server, rather than ordinary-suite passes.

Destructive migration cases hold the exclusive test guard and restore the baseline
before releasing it. Both schema fixtures and row-reset fixtures verify the permitted
live database/user. No migrations are applied automatically by application startup.
The application schema and public item contracts are unchanged. Repository callers
now own their transaction explicitly, as described in [Mutation transactions](transactions.md).
Controller logic remains in place; no item service layer is introduced.

Real constraint-rejection cases verify rollback after an earlier successful write.
Expiry tests hold actual MySQL protocol packets rather than simulating commit
results. Independent observer sessions distinguish uncommitted rows from rows
committed before an acknowledgement reaches the driver. A final test-fixture return
annotation correction addresses editor deprecation diagnostics without changing
runtime behavior; application code is unchanged after full-suite qualification.
Coverage describes application code executed in the parent test process; it is not
an aggregate of native application or Alembic subprocess coverage. MySQL migration
DDL is not claimed to be transactionally reversible. The database-package threshold
passes with online-command behavior verified separately through real subprocesses.

The image check uses the built artifact, production settings and its own ephemeral
MySQL project without host ports or development volumes. It does not establish
restart/storage durability, deployed failover, backups/restoration, historical-image
rollback, release promotion, or real ingress behavior. Request expiry prevents
commit only before the final activity boundary. Packet-barrier tests demonstrate
that a COMMIT already initiated can succeed after HTTP timeout and that a lost
acknowledgement does not establish rollback. No SQL-cancellation or automatic retry
safety guarantee is made; forced termination retains uncertain outcomes.

The obsolete required contexts `test-layers (integration)` and `test-layers (e2e)`
are no longer emitted. Remove them from existing GitHub rulesets and retain the
MySQL checks listed in [Branch protections](branch-protection.md). Local success and
workflow definitions do not establish hosted check execution or ruleset enforcement.

## Input fingerprints

| Input | SHA-256 |
| --- | --- |
| `app/common/handlers/request_activity.py` | `6f3b9257191c3069b1709b65e5f9f22f330c5d7c449bd211f03b24ec9748d7ee` |
| `app/common/handlers/application_route.py` | `fae3709781e5b37b45a8ca2a2dd90e5d78d0c83493d05028f52b87896be12e60` |
| `app/common/middleware/request_timeout.py` | `552fefb41985969e3fbf0b10463578fccde43ac995869505f7438ed49e620b3c` |
| `tests/integration/database/test_mutation_expiry.py` | `583e9dc012ea40afe65fe8e606c1052fb32aad9d446d5051d1a99417e11eac35` |
| `tests/unit/common/handlers/test_request_activity.py` | `90db446af5fb0ff43dc0be2c1d60ae7fd88b7117d64ca877db500e89781a8aa5` |
