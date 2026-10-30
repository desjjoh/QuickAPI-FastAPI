# Verification report

[Documentation index](../README.md#documentation)

## Source and environment

Verified on 2026-10-29 against base commit
`1c9ac3444940f168500928a63b302149c735c3f1` and the local fingerprints below.
The candidate includes uncommitted changes; the base commit alone does not identify
it. This report describes the current MySQL-only application and tests. Earlier
verification snapshots remain in Git history and do not define current support.

Windows uses Python 3.12.10. Linux uses Python 3.12.16 with disposable dependencies
and read-only source mounts. Persistence tests use guarded disposable MySQL 8.4.6.
The development database is separate and was not modified.

## Results

| Check | Result |
| --- | --- |
| Windows full MySQL suite | 997 passed; two POSIX-only cases skipped; five dedicated TLS cases deselected; 95.83% branch-measured application coverage |
| Linux full MySQL suite | 999 passed; no skips; five dedicated TLS cases deselected; 95.92% branch-measured application coverage |
| Database-independent units | 645 passed with an unreachable configured database target; no database-backed fixtures selected |
| Dedicated TLS | Five cases passed on Windows against the separate generated-certificate MySQL server |
| Coverage gates | Middleware 97%, lifecycle 99%, database package 95%, API 99%; all configured gates passed on both platforms |
| Formatting/linting | Black: 165 files unchanged; Ruff passed |
| Type checking | mypy: 68 application/tool files passed; strict Pyright: 5 affected files, zero diagnostics, using explicit installed typeshed |
| Dependencies | Local and fresh-image pip checks passed; removed optional database driver absent from both; pytest absent from runtime image |
| Transaction HTTP qualification | Existing 32-case preparation/ownership module and 23 real HTTP/MySQL expiry, uncertainty and rollback-loss cases pass in both full suites |
| Forced-exit diagnostics | Watchdog and repeated-signal paths terminate with status 1 even when stderr raises OSError or BrokenPipeError |
| Combined transaction shutdown | Expired marked mutations retain dependencies through rollback; cancellation-resistant mutations reach the final watchdog; original MySQL server sessions disappear |
| Final process assertions | Two combined cases passed again on Windows after strengthening dependency-order/watchdog assertions; Linux full suite includes those final assertions |
| Rollback connection loss | Real ROLLBACK command/acknowledgement loss invalidates the lease, preserves absence of the failed write, retires the server session and restores a queued caller on a replacement connection |
| Expiry and uncertain outcomes | Monotonic checks, expired acquisition without business SQL, caught cancellation, all four mutation methods after writes, real disconnects, held INSERT results, interrupted COMMIT, lost acknowledgement, confirmed commit before lost response, cleanup failure, invalidation and recovery |
| Transaction ownership | Four marked item mutation routes share one explicit request session; repositories never commit/roll back independently; read routes remain unmarked |
| Boundary guards | Existing owner/active factory session rejected; shared dependencies borrow without closing; completed owner cannot silently autobegin; streams/background tasks rejected and prepared error responses rolled back |
| Configuration | Only mysql+asyncmy accepted; test configuration remains independent of development .env |
| Migration behavior | Empty-schema rejection, baseline/model comparison, repeated upgrade, incompatible history, downgrade/reapply, offline SQL and real online commands pass against MySQL |
| Pool/session cleanup | Real MySQL late-connection disposal, queue/cancellation/invalidation, and server-session disappearance checks pass |
| Safety | Live identity checks, exclusive reset guards, destructive schema restoration, unavailable-target failure, and isolated command-lock tests pass |
| CI definition | Unit job, MySQL integration/E2E, full MySQL coverage, dedicated TLS and independent MySQL image qualification; YAML parses |
| Image-runner failures | Database startup, HTTP-check, and artifact-write failures all attempt disposable-project teardown |
| Built runtime image | sha256:55fa8176dfcaf129d3325ec49d8f676a6bd9d5f2607bc67b94486982e6e009a8 |
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
committed before an acknowledgement reaches the driver. Rollback barriers are armed
after initial connection setup so they interrupt rollback of an actual application
write. Combined process tests check that dependency teardown precedes service
cleanup and that stuck transaction work reaches the final watchdog, rather than
merely accepting any nonzero exit. Application code is unchanged after full-suite
qualification.
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
| `app/common/handlers/http_server.py` | `4dbe0a50ac441f2adf33272b6ba102210c24187d7d7852ed2e7c017f566a3203` |
| `tests/unit/common/handlers/test_http_server.py` | `8f19cbd7ad74fa823bf1e76675e192ba008fff74205c3694e7a7d43bc839f91a` |
| `tests/fixtures/shutdown_server.py` | `42585a05d37a96800f67845fd0e5d23d82b377f8f23c0c890f2d2a4d1887bdc5` |
| `tests/integration/test_shutdown_process.py` | `8c828decf9ebb99123cc41bf7d93668dc70a473308460197c7aafe76438ccc3d` |
| `tests/integration/database/test_mutation_expiry.py` | `750d619410d71f6f2b7400f4a2981a01902fac7649064266fe525d3962055d40` |
