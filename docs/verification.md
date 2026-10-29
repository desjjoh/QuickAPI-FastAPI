# Verification report

[Documentation index](../README.md#documentation)

## Source and environment

Verified on 2026-10-29 against base commit
`25d6be9c1565d3fafdc42a49676c0fa4430ed23d` and the local fingerprints below.
The candidate includes uncommitted changes; the base commit alone does not identify
it. This report describes the current MySQL-only application and tests. Earlier
verification snapshots remain in Git history and do not define current support.

Windows uses Python 3.12.10. Linux uses Python 3.12.16 with disposable dependencies
and read-only source mounts. Persistence tests use guarded disposable MySQL 8.4.6.
The development database is separate and was not modified.

## Results

| Check | Result |
| --- | --- |
| Windows full MySQL suite | 965 passed; two POSIX-only cases skipped; five dedicated TLS cases deselected; 95.67% branch-measured application coverage |
| Linux full MySQL suite | 967 passed; no skips; five dedicated TLS cases deselected; 95.77% branch-measured application coverage |
| Database-independent units | 638 passed with an unreachable configured database target; no database-backed fixtures selected |
| Dedicated TLS | Five cases passed on Windows against the separate generated-certificate MySQL server |
| Coverage gates | Middleware 97%, lifecycle 99%, database package 95%, API 99%; all configured gates passed on both platforms |
| Formatting/linting | Black: 162 files unchanged; Ruff passed |
| Type checking | mypy: 67 application/tool files passed; strict Pyright: 8 affected files, zero diagnostics |
| Dependencies | Local and fresh-image pip checks passed; removed optional database driver absent from both; pytest absent from runtime image |
| Transaction HTTP qualification | Final 32-case module passed on Windows and Linux, including MySQL error 1048 after preceding writes, refresh/model/response validation/render failures, pre-COMMIT failure, concurrent owners and response contracts |
| Transaction ownership | Four marked item mutation routes share one explicit request session; repositories never commit/roll back independently; read routes remain unmarked |
| Boundary guards | Existing owner/active factory session rejected; shared dependencies borrow without closing; completed owner cannot silently autobegin; streams/background tasks rejected and prepared error responses rolled back |
| Configuration | Only mysql+asyncmy accepted; test configuration remains independent of development .env |
| Migration behavior | Empty-schema rejection, baseline/model comparison, repeated upgrade, incompatible history, downgrade/reapply, offline SQL and real online commands pass against MySQL |
| Pool/session cleanup | Real MySQL late-connection disposal, queue/cancellation/invalidation, and server-session disappearance checks pass |
| Safety | Live identity checks, exclusive reset guards, destructive schema restoration, unavailable-target failure, and isolated command-lock tests pass |
| CI definition | Unit job, MySQL integration/E2E, full MySQL coverage, dedicated TLS and independent MySQL image qualification; YAML parses |
| Image-runner failures | Database startup, HTTP-check, and artifact-write failures all attempt disposable-project teardown |
| Built runtime image | sha256:2dc05611d47119e39fcccdfa7a1e3c52168afc6f5865fcec6a2378d36198a726 |
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

Full-suite runs and final focused fault qualification are separate observations.
The final fault module strengthens write-failure cases with actual MySQL constraint
rejection after an earlier write; application code is unchanged between those runs.
Coverage describes application code executed in the parent test process; it is not
an aggregate of native application or Alembic subprocess coverage. MySQL migration
DDL is not claimed to be transactionally reversible. The database-package threshold
passes with online-command behavior verified separately through real subprocesses.

The image check uses the built artifact, production settings and its own ephemeral
MySQL project without host ports or development volumes. It does not establish
restart/storage durability, deployed failover, backups/restoration, historical-image
rollback, release promotion, or real ingress behavior. Request expiry, cancellation during commit, post-commit failure and uncertain
outcomes retain their separate acceptance criteria. Before-COMMIT failure tests do
not establish rollback for a lost commit acknowledgement.

The obsolete required contexts `test-layers (integration)` and `test-layers (e2e)`
are no longer emitted. Remove them from existing GitHub rulesets and retain the
MySQL checks listed in [Branch protections](branch-protection.md). Local success and
workflow definitions do not establish hosted check execution or ruleset enforcement.

## Input fingerprints

| Input | SHA-256 |
| --- | --- |
| `app/common/handlers/application_route.py` | `6a510e5106246f1e8d2940a71e2ea0259f7ecbc44719355ef588b9d313467c1a` |
| `app/config/database.py` | `4abf6ded309f6dc157f3422e1b2817476e2155df72f82dfa1f0b8e695faa7da1` |
| `app/database/repositories/item_repo.py` | `5c1743e33cb5ad85f087f9f6cd28716fb0455da0cc4fd353690c9f519859948d` |
| `app/api/v1/items/controllers/item_controller.py` | `7bc2bd4cfb8ab88af993c891e8129e57df00cfdbc549cb2f355113371d54eb5f` |
| `tests/integration/database/test_item_repository.py` | `e9358b3118432c358cfe9edbec762bf2a47d25355028116164434d7c7e679924` |
| `tests/integration/database/test_transaction_routes.py` | `3cb588c14f3b4e393f63d8337da488fe1a7b28269a92fee920a9ffa4ffd6875d` |
| `tests/unit/config/test_database_config.py` | `e47c404dc75f87e0950f4e9559d41341e1ea45367fabc1d064b28cd81eada552` |
| `tests/unit/common/handlers/test_application_route.py` | `c62b431d240e5c1926dcef8c113694964ff5075b4b1f597a5378052cae81055d` |
