# Verification report

[Documentation index](../README.md#documentation)

## Source and environment

Verified on 2026-10-29 against base commit
`b014519cf764a4d3d518339e6b20748d36778b99` and the local fingerprints below.
The candidate includes uncommitted changes; the base commit alone does not identify
it. This report describes the current MySQL-only application and tests. Earlier
verification snapshots remain in Git history and do not define current support.

Windows uses Python 3.12.10. Linux uses Python 3.12.16 with disposable dependencies
and read-only source mounts. Persistence tests use guarded disposable MySQL 8.4.6.
The development database is separate and was not modified.

## Results

| Check | Result |
| --- | --- |
| Windows full MySQL suite | 922 passed; two POSIX-only cases skipped; five dedicated TLS cases deselected; 95.60% branch-measured application coverage |
| Linux full MySQL suite | 924 passed; no skips; five dedicated TLS cases deselected; 95.69% branch-measured application coverage |
| Database-independent units | 631 passed with an unreachable configured database target; no database-backed fixtures selected |
| Dedicated TLS | Five cases passed on Windows against the separate generated-certificate MySQL server |
| Coverage gates | Middleware 97%, lifecycle 99%, database package 96%, API 99%; all configured gates passed on both platforms |
| Formatting/linting | Black: 159 files unchanged; Ruff passed |
| Type checking | mypy: 66 application/tool files passed; strict Pyright: 21 affected files, zero diagnostics |
| Dependencies | Local and fresh-image pip checks passed; removed optional database driver absent from both; pytest absent from runtime image |
| Configuration | Only mysql+asyncmy accepted; test configuration remains independent of development .env |
| Migration behavior | Empty-schema rejection, baseline/model comparison, repeated upgrade, incompatible history, downgrade/reapply, offline SQL and real online commands pass against MySQL |
| Pool/session cleanup | Real MySQL late-connection disposal, queue/cancellation/invalidation, and server-session disappearance checks pass |
| Safety | Live identity checks, exclusive reset guards, destructive schema restoration, unavailable-target failure, and isolated command-lock tests pass |
| CI definition | Unit job, MySQL integration/E2E, full MySQL coverage, dedicated TLS and independent MySQL image qualification; YAML parses |
| Image-runner failures | Database startup, HTTP-check, and artifact-write failures all attempt disposable-project teardown |
| Built runtime image | sha256:d8e10ed310816c72c7f2089f72fb1e5071a70f5c7b3101d5a3e0a66d24cf4b84 |
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
The application schema and public item contracts are unchanged by this candidate.

Coverage describes application code executed in the parent test process; it is not
an aggregate of native application or Alembic subprocess coverage. MySQL migration
DDL is not claimed to be transactionally reversible. The database-package threshold
passes with online-command behavior verified separately through real subprocesses.

The image check uses the built artifact, production settings and its own ephemeral
MySQL project without host ports or development volumes. It does not establish
restart/storage durability, deployed failover, backups/restoration, historical-image
rollback, release promotion, or real ingress behavior. Mutation transaction/response
ownership and commit uncertainty retain their separate acceptance criteria.

The obsolete required contexts `test-layers (integration)` and `test-layers (e2e)`
are no longer emitted. Remove them from existing GitHub rulesets and retain the
MySQL checks listed in [Branch protections](branch-protection.md). Local success and
workflow definitions do not establish hosted check execution or ruleset enforcement.

## Input fingerprints

| Input | SHA-256 |
| --- | --- |
| `.env.example` | `5a61cf37523c709bc1f138fa087c97b4a0880f3a783ea89113786948c2ec3689` |
| `.env.test` | `40b9e30608e524d56ab09d350a1024d5cba38ce643721eb60fe0460538d48802` |
| `.github/workflows/tests.yml` | `1cdb0198dc97fc2830bd47dd20db2f268395c338e1a584d7d836459ea01ae284` |
| `app/config/database_transport.py` | `3d764ace86c056037f9aba47c9cfe47cbeffaf16dce114a4ed8bb4ad5a63b80c` |
| `app/config/environment.py` | `482aa4b1592c6c12584d1ac3497f328a1b1508a423e903c07d1fad7d0a4036f3` |
| `app/config/logging.py` | `4320122b28888ab05bf1e2d901c9a8c2656d72c79dbac0bc525d0db1902e61ba` |
| `app/database/migrations/env.py` | `da83f8cbaafc0f4db39dc6039c57045e5673ec82ccd4fe269f0529805281dc90` |
| `docker-compose.smoke.yml` | `b19857fb64f7b62278a9253f43e6e7ec6d735fdd49fa80466840eddfd645f1af` |
| `requirements.txt` | `10fc9509811475c290a469a1e004b729cdefa4ca233014f4cb1458f3d620725e` |
| `scripts/test_database_tls.py` | `9fa10f9864a3e344b251f173178eaa4612d04c36d85ddb74c17e6ef58b8f3b4e` |
| `scripts/test_db.py` | `a5008cbfa751b3926bb84c51783fbcccd9af7a54bf62f1f0fba18198d71c98f8` |
| `scripts/test_image.py` | `e326c018c3836fbde04775a4eb8a0860094937d2753b601305654bae0fd0c386` |
| `tests/conftest.py` | `f52c8bb7c8a8e89eff5552cb45a6ff101c60c3952767408428ec1e016ba79dac` |
| `tests/fixtures/migrations/env.py` | `1194f6371854f82321dbc853e8b66f4d1f6287af6fc670b7c934d410ced803fd` |
| `tests/integration/database/test_database_capacity.py` | `15cd326c1b89861e08958613d67912bd6c6c25e733f5b5ac2f6043497f05485d` |
| `tests/integration/database/test_database_isolation.py` | `b695ae5717555d970e7106e34b266cb43428071061ead28a6353d98e7a673cf5` |
| `tests/integration/database/test_database_recovery.py` | `ef013c2c016bf81b17c36323b4155d8f6e4279270227c3e688338430ae80bf29` |
| `tests/integration/database/test_migration_evidence.py` | `5be9bedbbd3d4b046b9f4b1cbf4ed1ade6ab8dfd36f7eace23e09a164f148ff8` |
| `tests/integration/database/test_migrations.py` | `1a985128d686457a9f3fdf079508c2fd0d1efc5a7def56dd56302c60debd207b` |
| `tests/integration/errors/test_error_responses.py` | `1ff9b335a31bc12710ef4d59f21f149f84ebcb8331e6186ce7fbc38dd94553d9` |
| `tests/integration/middleware/test_logging_privacy.py` | `9df2049b46f6f9cdaeb88fdcc868d56fd7275377e9558c8a0d16fc3215bc8336` |
| `tests/unit/api/v1/items/models/test_pagination_query_model.py` | `3e492431a2e4bd477b3bf9e6df04a5fec5e9cfbc4b779006b21e4d090423d63d` |
| `tests/unit/config/test_database_transport.py` | `9c743e607dbb39529761c7d5089f56ef9d1ffb747719361a4a41b3fce8501136` |
| `tests/unit/config/test_disposable_database.py` | `e753f013d70159e7c16b2a3cfc449ae2b8596e65a58222cda10676f4f4fe7fa8` |
| `tests/unit/config/test_environment.py` | `6e9d82bff2a3da773e4f316da950e992e41325efd15d0589a721421f6399e84b` |
| `tests/unit/config/test_image_qualification.py` | `014c8fd87d42046efa3411306913ca829ca542224a468b7edc2ccd72e0668670` |
