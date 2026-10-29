# Verification report

[Documentation index](../README.md#documentation)

## Database readiness and recovery verification

TLS infrastructure follow-up on 2026-10-29: the hosted TLS server failed before
pytest because the Linux temporary certificate directory was not traversable by
the container's MySQL user. Certificate generation now explicitly sets directory
mode `0755` and file modes `0644` for these disposable credentials. A Linux
cross-UID check reproduced rejection at `0700` and successful key access at `0755`;
five TLS cases passed against MySQL reading the corrected files from a Linux
Docker volume. The normal Windows TLS command also passed all five cases, and the
new certificate-generation regression test passed locally. Ruff, Black and mypy
checks passed. Temporary verification resources were removed. Hosted CI must be
rerun; the following suite counts predate this additional regression test.

Verified on 2026-10-29 against base commit `daf010aab02352f4468ef495fa4c3148a92f7c38`
and the local inputs fingerprinted below. These results include uncommitted changes.

| Check | Result |
| --- | --- |
| Windows compatibility | 899 passed; one MySQL-only socket case skipped; five dedicated TLS cases deselected; 95.99% branch-measured application coverage |
| Linux compatibility | 899 passed; same skip/deselections; 96.09% branch-measured application coverage |
| Windows MySQL | Integration 168 passed; E2E 113 passed |
| Linux MySQL | Combined integration/E2E 281 passed; 143 shared database-backed cases |
| Dedicated TLS regression | Five passed on Windows; independent server/certificates removed afterward |
| Probe ownership | Concurrent callers share work; caller cancellation is isolated; healthy/failed cache expiry, stopped state, cancellation and owned-lease invalidation pass |
| Startup | Revision failure, acquisition timeout and cancellation propagate after cleanup; existing missing/incompatible-history checks pass |
| Real HTTP / MySQL | Same running API recovers from three outages, a killed idle session, a stalled response and repeated exhausted acquisitions; liveness and item reads verified |
| Resource evidence | Probe connection disappearance checked through MySQL process list; admission counts/waiters and test relay resources return to baseline |
| Coverage gates | Middleware 96%, lifecycle 99%, database package 100%, API 99%; configured gates passed on both platforms |
| Static/editor checks | Black 150 files; Ruff passed; mypy 63 application/tool files; strict Pyright ten affected files, zero diagnostics |
| Production-image smoke | Locally built image `sha256:a8e2efc5600a74d5d598b8e4e55a72597f17123b733e9100433461b16cd86cbc`; SQLite explicit migration, readiness, item read and pip check passed |
| Hosted CI / release | Not run / not verified for this candidate |

Linux verification used disposable dependencies with read-only source mounts.
MySQL checks used the guarded disposable test database. The real socket case is
explicitly skipped by SQLite compatibility runs and executed in the existing MySQL
integration selection. Successful checks do not qualify deployed failover,
backups, application-wide draining, arbitrary query cancellation, or MySQL
release-image smoke behavior. Runtime probes do not retry business mutations.
The local development database was not modified. Temporary image smoke resources
were removed; the pre-existing regular test database was retained.

| Input | SHA-256 |
| --- | --- |
| `.env.example` | `250e9f8dee256573a5b2be62ae268c727f193dbeb432df54e7d509bc0b1d53b3` |
| `.env.test` | `4d4c869fb887c6bec49b4c17e365eac109f9ca524d79f96550f577eab42b3a93` |
| `app/common/handlers/database_readiness.py` | `829a82ef2dea397829ee202599edfe336b3848461279ca0186e67ae7f221b96b` |
| `app/config/database.py` | `b9543c2fec7fc4622181bccbbb2a4c66f117dd5bc57133ed85e5a1734004c52f` |
| `app/config/environment.py` | `d76484ac12a564116358278d062c35dc1fac103f0da62f1eb5d97e5edcc8cd6b` |
| `tests/conftest.py` | `81f021e9d941a3a5f15d300c6c3004c05e643ddd299d578f53d0c89226743774` |
| `tests/e2e/conftest.py` | `d67e8e08726c9ccac36f031824f83c78366a49441805389b0c14624630448a1b` |
| `tests/e2e/test_application.py` | `ee1d1c5ff6e3e20f338186d55485b7845e7f789dc00e6c9ddf6a20ca95358544` |
| `tests/unit/config/test_database_config.py` | `7fe2f0bca40811f40610363ddf9029b79d97035fe09fe70a143871e5b3b1e2d1` |
| `tests/unit/config/test_database_transport.py` | `f1657da84e5ec7c6cd18f35a804a0d85fadfea475132f1900f7ffb4c403b81e8` |
| `tests/unit/common/handlers/test_database_readiness.py` | `06d937ed4067a0f8d14294c90aea4c0eba8b9da88223462c796bc7b86b54adf5` |
| `tests/integration/database/test_database_recovery.py` | `095a768f4b13ad210dfdb065b8fa9cb355bc68c07d7de09d709849ab7968d95f` |

## Database capacity and transport verification

Verified on 2026-10-29 against base commit `0f005e437efeb04d639a7b5da6fcea807f1042d3` and the local input fingerprints
below. The base commit alone does not identify these changes.

| Check | Result |
| --- | --- |
| Windows complete compatibility suite | 872 passed, 5 dedicated TLS cases deselected; Python 3.12.10; 95.94% branch-measured coverage |
| Linux complete compatibility suite | 872 passed, 5 dedicated TLS cases deselected; 96.05% branch-measured coverage |
| Windows MySQL | Integration 166 passed; E2E 113 passed |
| Linux MySQL | Combined integration/E2E 279 passed; 141 shared database-backed cases |
| Dedicated TLS | Five cases passed on Windows and Linux, separately from compatibility suites |
| Static checks | Black: 147 Python files unchanged; Ruff passed; mypy: 62 application/tool files passed |
| Editor typing | Strict Pyright: 17 affected Python files; zero diagnostics |
| Coverage gates | Middleware 96%, lifecycle 99%, database package 100%, API 99%; configured gates passed |
| Configuration | Defaults, strict syntax/ranges, CA/SSL relationships, env examples, and invalid certificate configuration verified |
| Pool behavior | Fixed cap/no overflow, bounded waiters, timeout/cancellation, slot-handoff cancellation, invalidation, queued disposal, late connection rejection, recreation and capacity recovery verified |
| Socket behavior | Stalled greeting, external cancellation, TLS-negotiation stall: peer closure and admission recovery verified |
| HTTP behavior | Real ORM pool exhaustion returns safe 503 envelope and fixed message |
| TLS trust/identity | Trusted cipher accepted; wrong CA and wrong IP identity rejected; missing cipher fails closed |
| Windows TLS | Pinned asyncmy upgrade fails on Proactor; supported entrypoints select compatible selector loop; native API and Alembic TLS checks pass |
| Runtime image | `sha256:71594fba19fb1b6a690128c35ed75461e6920415149d602ee3ec877039a255cb` built locally |
| Image smoke | Explicit SQLite migration, readiness, item read, and `pip check` passed |
| CI definition | Existing MySQL integration matrix job includes dedicated TLS command; YAML parses |
| Cleanup | Generated TLS certificates, TLS project, and image smoke resources removed; existing development/test MySQL services retained |
| Hosted CI / release | Not run / not verified for these changes |

SQLite keeps its existing driver/pool behavior. Compatibility tests additionally
exercise the admission adapter with a test-only SQLite pool. MySQL fixtures and
commands use the actual shared bounded transport factory. TLS qualification uses
an independent MySQL 8.4.6 server, temporary CA/server certificate, and explicit
marker selection; default deselection is not represented as a TLS pass.

Linux runs use disposable tool installations and read-only source mounts. The
typed test-double adjustment and TLS-context assertions were separately rerun after
the complete suite. Both platforms reran the dedicated TLS cases with certificate
rejections required to contain an actual certificate-verification failure.
Application coverage is not an aggregate of the dedicated TLS subprocesses.
Connection/acquisition deadlines do not establish SQL cancellation, transaction
rollback, application draining, stale-session recovery, deployed CA rotation,
fleet capacity, or MySQL release-image qualification. The image smoke remains
SQLite-based. These boundaries retain their separate roadmap acceptance criteria.

| Input | SHA-256 |
| --- | --- |
| `.dockerignore` | `a1eb3f4f1b565e7030327bf38771ba5fd85b412c323c2b94e802c13ddcc745b0` |
| `.env.example` | `8a706620e36edb193d79668d8d77c1f24274d57f3e90f2087911206ae7920b9f` |
| `.env.test` | `6e7ca8cbe642c570a87b9c7a39dc67a1e938fbb4ee229e504cc4b5ca1c036b44` |
| `.github/workflows/tests.yml` | `0b7d7ed6029a9ba9657f1d01a6b71ac6bfcb4767729badaa9fa8e38111db5fb1` |
| `app/common/handlers/database_pool.py` | `85f9758179a696d64e7544800d9194519f75eec759c0278d4e119ccc5fefc355` |
| `app/common/helpers/error_diagnostics.py` | `83662f63fe10211406f0812101e592ba1ed1213034ec44995ffe7e83f6bf8dd0` |
| `app/config/database.py` | `48fa0ca5ba35b5f9d2aa586e1ef236b8b304ff671a9fa9691f93614fad9f8537` |
| `app/config/database_transport.py` | `3f502242a5c71c69c490caecc716c8f8260c690ce2fec0c49ac48efeaf9406d0` |
| `app/config/environment.py` | `5186fb0e6a12b0d8f84c1c1a1dd8fdd99cf4e8894657527efbdf563443b5dac4` |
| `app/config/event_loop.py` | `441c820fea66770a383bf065516db8cccbbfe9453b45778f09fa4ec7defc1758` |
| `app/database/migrations/env.py` | `5d7bd0915bbaace8140636dee96e8f0e7155c468ff8043dd09f4d7d461f9e4d2` |
| `app/main.py` | `5d335c15d166fe40eac5648792257bb9e26f045e55ce88ca88cb4272d1b23a15` |
| `docker-compose.test.tls.yml` | `c7c06caea9cb7a7a2fbe08322c41423a85b72c3f5afdbaa54c0a198fbdf69ec1` |
| `pyproject.toml` | `e553f7d09e9f62cd8a6fdecd00492e138ef75dc723eb01aed6793196824ebabe` |
| `scripts/test_database_support.py` | `a6885c5ebbc3542dd1e2bf5a6999d02ddef809f16256036a42df670bb514ac09` |
| `scripts/test_database_tls.py` | `c65ba07f20098156589671b044b6a9157efe2a289597583af22901a87c71e2fc` |
| `scripts/test_db.py` | `92cb14350a49b44839f01b6bb21d933370993ffd116e40061162e6381bab924b` |
| `tests/conftest.py` | `cb3dc7c13060517ae71deca6908757036cf0d69a759896bbd8feac5db65402c4` |
| `tests/integration/database/test_database_capacity.py` | `83b1ae28057592d9d1e0b33a79dd88327ef27cb8270ec8fa6910bfba59fa948a` |
| `tests/integration/database/test_database_tls.py` | `ca87f531645e6a203c3a4ed23390a31f332f20f90c48f0def91766a157953625` |
| `tests/unit/config/test_database_transport.py` | `65c3bab9f38449e3c3979f025d266b6830613cf3c075b946658aae007ba65d81` |
| `tests/unit/test_database.py` | `0df1db1de72a47244ce966ed766a53da1c38e338782568b0790e2ae61cc04e6f` |
| `tests/unit/test_main.py` | `39a9acb29c36d095a58f8848cba29caf2ac412f2df666fb64d7f6cc150de48e0` |

## Migration upgrade and rollback evidence

Verified on 2026-10-29 against base commit `d258d6f20817600d9555bbc7e2533ff66285f378` and the local inputs below.

| Check | Result |
| --- | --- |
| Windows / Linux complete compatibility suites | 828 passed each; coverage 96.22% / 96.33% with branch measurement |
| Windows disposable MySQL | Integration 160 passed; E2E 113 passed |
| Linux disposable MySQL | Combined integration/E2E 273 passed; 140 shared database-backed cases |
| New evidence cases | Nine cases run against SQLite and MySQL |
| Static checks | Black 140 files unchanged; Ruff passed; mypy 58 application/tool files passed on Windows |
| Editor typing | Strict Pyright: evidence module and four fixture files, zero diagnostics |
| Real baseline | Disposable downgrade deletes table/rows; fresh upgrade matches model metadata |
| Additive evidence chain | Original IDs, names, prices, nullable descriptions, timestamps preserved; backfill, default, non-null metadata and index verified; downgrade/reapply pass |
| Partial DDL failure | On MySQL, created artifact remains and evidence history does not advance; known artifact explicitly cleaned |
| Drift / history | Missing index and extra column detected despite matching history; older/newer/unknown revisions and multiple source heads rejected |
| Startup compatibility | Incompatible history prevents lifecycle readiness; restored expected revision permits startup |
| Final test schema | Application history and schema comparison restored; existing disposable test service retained |
| Hosted CI / image qualification | Not run / not repeated for this change |

The evidence chain is test-only, with separate version history and temporary script
directories. It does not add an application field or real revision. Both SQLite and
MySQL execute it through the existing isolated fixtures; MySQL writes hold the
disposable-target lock. No development/shared database is reset. Results establish
the listed baseline/examples, not correctness of future migrations, historical
application-image rollback, transactional MySQL DDL rollback, or backup restoration.
The current strict-revision policy requires stopped-application migration ordering.
Earlier verification sections retain their own scope.

| Input | SHA-256 |
| --- | --- |
| `app/config/application.py` | `eb087d26c0dba86dff70e13fa76e1b4a973f7ba55aac452edd219301effa6ecc` |
| `tests/e2e/test_startup_logging.py` | `3e5d190c8e5fd7a25bc4baad3205a0828e937667a4939d3f402405c93d1b5faa` |
| `tests/fixtures/migrations/backfill.py` | `3b02759c1c03a3a4d44beb296d41892b35cf72c0227bb26c4ca957a33438b19d` |
| `tests/fixtures/migrations/base.py` | `d41454f85acdb6854090d68a824c44f30296f1a5950b381769126e0e9e601721` |
| `tests/fixtures/migrations/env.py` | `a75447ecb18aee06d9331158a34f6e2b07d42f38f8cb63d1492abeb08b80a52d` |
| `tests/fixtures/migrations/failure.py` | `c4a6fb3274649e3f3233eaeb5c8140b00c81e2bd977616223e8a63782b8d9c55` |
| `tests/integration/database/test_migration_evidence.py` | `db01649f233ebab80e2630bd36bad833f78a3cb59d353c7a3a3cec2b0e09f89f` |

## Startup logging verification

Verified on 2026-10-29 against base commit `d258d6f20817600d9555bbc7e2533ff66285f378` and the local inputs below.
The boot banner precedes service registration during application construction;
services start only when the lifespan begins. The regression test verifies one
banner, ordered registration/startup/HTTP messages, and service shutdown.

Windows Python 3.12 checks: 819 complete-suite tests passed with 96.22% overall
branch-measured coverage; 18 focused application/lifecycle tests passed. Black,
Ruff, mypy, and strict Pyright (two affected files, zero diagnostics) passed.
Linux, MySQL suites, runtime-image smoke, and hosted CI were not repeated for this
logging-order change. Earlier results retain their own source scopes.

| Input | SHA-256 |
| --- | --- |
| `app/config/application.py` | `eb087d26c0dba86dff70e13fa76e1b4a973f7ba55aac452edd219301effa6ecc` |
| `tests/e2e/test_startup_logging.py` | `3e5d190c8e5fd7a25bc4baad3205a0828e937667a4939d3f402405c93d1b5faa` |

## Required-check configuration confirmation

On 2026-10-29, the maintainer confirmed completing the required-check update after
receiving the eight-context list, including both MySQL matrix checks. This is a
maintainer-reported configuration result, not an independent ruleset inspection or
a hosted CI pass. Historical observations below retain their original scope/date.

## Disposable MySQL verification

Verified on 2026-10-28 against base commit `e3be0d0ce098e3ee2b1b1ee01950a87102ca15ab`
and the local input fingerprints below. The base commit alone does not identify
the locally tested changes.

| Check                                 | Result                                                                                                                                                        |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Windows compatibility suite           | 818 passed; Python 3.12.10; 96.22% overall coverage with branch measurement                                                                                   |
| Linux compatibility suite             | 818 passed; 96.33% overall coverage with branch measurement                                                                                                   |
| Windows MySQL integration             | 151 passed; 24 database-backed tests use shared MySQL fixtures                                                                                                |
| Windows MySQL E2E                     | 112 passed; 107 database-backed tests use shared MySQL fixtures                                                                                               |
| Linux MySQL integration               | 151 passed; 24 database-backed tests use shared MySQL fixtures                                                                                                |
| Linux MySQL E2E                       | 112 passed; 107 database-backed tests use shared MySQL fixtures                                                                                               |
| Target-safety/wrapper regressions     | 38 focused tests passed; also included in complete compatibility suites                                                                                       |
| Formatting / lint                     | Black: 134 Python files unchanged; Ruff passed on Windows and Linux                                                                                           |
| Application/tool typing               | mypy: 58 source files passed on Windows and Linux                                                                                                             |
| Editor typing                         | Strict Pyright: 11 affected Python files; zero diagnostics                                                                                                    |
| Coverage gates                        | Middleware 96%, lifecycle 99%, database package 100%, API 99%; configured gates passed                                                                        |
| Dependencies                          | Native and disposable Linux environment `pip check` passed                                                                                                    |
| Test infrastructure                   | MySQL 8.4.6; project `quickapi-fastapi-test`; host port 3311                                                                                                  |
| Temporary storage                     | Docker `HostConfig.Tmpfs` confirms `/var/lib/mysql` is tmpfs                                                                                                  |
| Migration commands                    | Fresh upgrade, current revision, comparison, downgrade/reapply, and test-target proposal generation passed                                                    |
| Proposal cleanup                      | Generated verification-only revision removed without application; original chain/model comparison restored                                                    |
| Isolation                             | Real commits/fresh-session visibility, clean rows, constraints, live identity, and competing MySQL lock checks passed                                         |
| Failure behavior                      | Unsafe targets rejected; unavailable MySQL fails; no-database selection rejected; migration/collection/test failures retain failure exits and attempt cleanup |
| Local concurrency                     | Cross-process wrapper exclusion/release verified on Windows and Linux                                                                                         |
| Env separation                        | Explicit MySQL settings ignore a deliberately invalid development `.env`; development connection/comments retained                                            |
| CI definition                         | YAML parses; separate MySQL layers gate combined coverage and downstream container qualification                                                              |
| Cleanup                               | Temporary test containers/network removed; development MySQL remains healthy on port 3310                                                                     |
| Hosted CI / branch enforcement        | Not run / not verified                                                                                                                                        |
| Runtime-image smoke for these changes | Not repeated; production-image MySQL qualification remains separate                                                                                           |

Complete compatibility suites default to SQLite. MySQL layer totals also contain
database-free HTTP/lifecycle cases and intentionally isolated SQLite migration/file
checks; the database-backed fixture counts identify the 131 cases using MySQL.
Linux verification uses read-only source mounts, disposable tool installations,
and temporary coverage/cache/test files. Application coverage gates do not measure
the repository wrapper's coverage; its safety/failure tests are listed separately.

Local orchestration exercises the documented Python wrapper. Linux MySQL tests use
the same guarded fixtures against the isolated container's internal service address.
No development/sibling database was migrated or reset by test helpers. This evidence
does not qualify future representative data upgrades, pool/TLS capacity, outage
recovery, a MySQL production image, or hosted deployment/release behavior.

### Disposable test input fingerprints

| Input                                                   | SHA-256                                                            |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `.dockerignore`                                         | `20ec97ff95653f24c6ded6ef61542b0f49b36d1cb525acbcf9ea2a26707e31fe` |
| `.env.example`                                          | `61376768420bded1cc8e3bda7368ab51511fc8d27744d53f2eb20b2a384c883c` |
| `.env.test`                                             | `0d6167f86f9f423939bb25144bfeda31e55a57c48264683f851a8f77ee34123a` |
| `.github/workflows/tests.yml`                           | `2a460302db035110b09d07b456c0906d72d8fc45fc8ff9c1e8af5fe261d49c9c` |
| `app/config/environment.py`                             | `36bec2cf154827ac6eafa9717be072ddeb1cb13474184cbd695d720abcacc72f` |
| `docker-compose.test.yml`                               | `5f81a3ed73a658efde8ccf752b042d538784920c9e9c2327bcb17244bf7173e1` |
| `scripts/__init__.py`                                   | `55028c82422c38a3d6e0b12e2769bd09981168acd0597531204d1cfc7464c2a2` |
| `scripts/test_database_support.py`                      | `9da474498f59d3590eaecba90660bdd0ee9255d1e599c4be3cc83a4917c5b20f` |
| `scripts/test_db.py`                                    | `66affddc45d936b5fc2dd93c9a4660b066024c6e1f42240937c8308194179033` |
| `tests/conftest.py`                                     | `7a41dd9e00364ae850b21424aecca7f40811d18ab95ff618c8bd009a687f9e0f` |
| `tests/e2e/conftest.py`                                 | `94f851572ac04f1deba9348370159c15e2fecec7daebe489f04e992ad7e4ed8e` |
| `tests/e2e/test_application.py`                         | `4a89bc4d7395cb7edf8641c2f79219bfa7130090190cdbabf8ed85b2f7479ba4` |
| `tests/integration/conftest.py`                         | `90d964cab808b753f4ea43ce63a95bbf04f3ee3af9c8fe91d7cdcec2c67e8e75` |
| `tests/integration/database/test_database_isolation.py` | `bf8cdadb0b33f10392c570b9f7f306296e3952f541cdcf2c74273a98a5c6bacd` |
| `tests/integration/database/test_item_repository.py`    | `f282fa75160dbb1af3c3a709e0f92923bba38f0aad39ca91828ffb5cda123f47` |
| `tests/unit/config/test_disposable_database.py`         | `134764fa243b1af92ac3cee341bcdc00f0fc583d1a4a64531b9a0bd5e3bf0ec4` |

## Migration foundation verification

Verified on 2026-10-28 against base commit
`1e4f413096a4c9f53546c3aed2c601d2dac45f5f` and the local input fingerprints below.
The base commit does not include these local changes.

| Check                    | Result                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------ |
| Windows complete suite   | 776 passed; Python 3.12.10; 96.21% branch coverage                                               |
| Linux complete suite     | 776 passed; 96.33% branch coverage; disposable container, read-only source mount                 |
| Formatting / lint        | Black: 129 Python files unchanged; Ruff passed on Windows and Linux                              |
| Application typing       | mypy: 55 source files passed on Windows and Linux                                                |
| Editor typing            | Strict Pyright: 13 affected Python files; zero diagnostics                                       |
| Dependency consistency   | Native environment and runtime image `pip check` passed                                          |
| Coverage gates           | Middleware 96%, lifecycle 99%, database package 100%, API 99%; configured gates passed           |
| Baseline                 | Fresh schema matches models; repeat upgrade preserves a representative row                       |
| Startup rejection        | Empty/missing/incompatible history rejected; empty database tables remain uncreated              |
| Migration commands       | Online async execution, offline SQL, downgrade/reapply tested on disposable SQLite               |
| Docker MySQL             | Isolated `quickapi-fastapi-dev` project/database; MySQL 8.4.6; loopback port 3310                |
| Native MySQL API smoke   | Readiness, item creation (201), and readback passed                                              |
| Container MySQL smoke    | One-shot migration exited 0 before API became healthy; item read passed                          |
| MySQL persistence        | Container recreation retained the sample row and revision; no volume reset performed             |
| MySQL comparison         | Native and final-image `alembic check` report no new operations                                  |
| Final runtime image      | `sha256:a41b9b8bb902cf7d7aab84b66d540f02c2491b85de26f1a57415529f20b87ccd`                        |
| Final SQLite image smoke | Unmigrated startup fails with command guidance; explicit upgrade enables readiness and item read |
| Cleanup                  | Temporary smoke volumes/containers removed; temporary API stopped; development MySQL retained    |
| Hosted CI / release      | Not run / not verified                                                                           |

Runtime migration helpers are included in the image; development analysis/test tools
are installed only in the disposable Linux verification container. The automated
persistence suites use SQLite. Local MySQL smoke does not establish a full MySQL CI
suite, schema-drift detection, representative future backfills, deployment rollback,
capacity/TLS qualification, or outage recovery. Startup checks revision equality,
not every table/column. No shared Express/NestJS database was migrated or reset.

### Migration input fingerprints

| Input                                                   | SHA-256                                                            |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `.env.example`                                          | `b44d09cb3da1557ebe7b3da7ee4f8a2eafc769617ebf3c7c96a16de188748356` |
| `.github/workflows/tests.yml`                           | `2bf960a93058556d0319140b3822ff50fd637b00c7f6a0be44a811f5b5e635db` |
| `Dockerfile`                                            | `71eedddc4f3e2d4e492eae66b7f4c7ab88aff73cced3c7a56bb7aad2b8297924` |
| `alembic.ini`                                           | `3f61cffc8fabca9774d67e3dfd9516c858c4da98aaefec26f643e2610f654b2f` |
| `app/config/database.py`                                | `b04853d6d6ee355a0b97d66776e6ed42d9b2d5f56bcfaefa9a24b138d7f5ba35` |
| `app/config/environment.py`                             | `614ee4f67976c9b217838d29414d56b128d0370042efacfcaf7efbcf891f3200` |
| `app/config/migrations.py`                              | `16decaf23eaeb9f9c4c70a66cf97bbfb60b0fde3fcf3a48ad1b9245835bf3539` |
| `app/database/migrations/env.py`                        | `aa006a88455a144599689e614a5d9a43dd166b138287af43761edad5384c7589` |
| `app/database/migrations/script.py.mako`                | `9c72f2b9aa664f849982dd50ae87f788bd81a5270898624dfd0a6b2703da561e` |
| `app/database/migrations/versions/0001_create_items.py` | `518ecf75af75ef5faca34d4f43a59ef92f6f1a2e26932a23f7c4f9a4625f58cf` |
| `docker-compose.yaml`                                   | `cdbf0944b3a07294fc5a32100b38009668c1937f15df977c4b583ece271baec5` |
| `requirements.txt`                                      | `387fb4e096e60eba5fdd66fc582fbbf68677a6e44ecd6e26dd76310ec11a19e6` |
| `tests/conftest.py`                                     | `3b71c4771f0c0149063cab3b444d378b46c2c54539cdbb3153035a32246589f7` |
| `tests/e2e/conftest.py`                                 | `1f80afde2b94f388ebcdfd2e635bc7d33fc5a86252d2f85fb8ca7df114f7c05e` |
| `tests/e2e/test_application.py`                         | `c1e590fe8892a47bc1e22994055c4488f30ca3913dc95067aed3ed127002e47b` |
| `tests/integration/conftest.py`                         | `1006f49cc94cee1092a9fa88ea99bc7ea041bae105ae7d5030a80c294996c0c8` |
| `tests/integration/database/test_item_repository.py`    | `daf763cf8ff7fa51e64e4435ef3e404764807affa527e367fbf71aad828dc16f` |
| `tests/integration/database/test_migrations.py`         | `138c7be87a6a4777c926f15c988f1ce71240868b5f4ebc50427e72de270ef4f3` |
| `tests/unit/config/test_database_config.py`             | `11b4ea5cd9c4794766ebc2fa05f8b55b25c1a7f2f626c73df0c95013afefe797` |
| `tests/unit/config/test_environment.py`                 | `cc25bc245ee48171d4b211b75dd285940374d7c26c7bc21b87dd1c719e3202d7` |

## Dependency logging filter verification

Verified on 2026-10-28 with the Windows Python 3.12 environment, against base commit
`2d19fc60440e5805d0c7b1706540281ef57678ab` and the local inputs below.

The focused logging suite passes 24 tests. Ruff, Black, and mypy pass for the affected
Python files (mypy covers the application module). Fresh-process checks at DEBUG,
INFO, WARN, and ERROR verify that unlisted dependencies and explicitly enabled
child loggers cannot emit DEBUG/INFO records, real warnings retain WARNING,
errors retain ERROR, and application DEBUG/lifecycle filtering remains independent.
Complete suites, Docker smoke, and hosted CI were not repeated for this filter change;
the complete-suite results below belong to their recorded snapshot.

| Input                                                  | SHA-256                                                            |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| `app/config/logging.py`                                | `7cbfa7efd5338ffe0d0125ad18862dff4c2f7776d8825af6ba0bcfef6e02af9a` |
| `tests/integration/middleware/test_logging_privacy.py` | `8de694af15ccff97554357fc1ef462193d74cac85dae2fb8ba9e2158d38da1a1` |

## Scope and source identity

| Field                                           | Verified scope                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------------------ |
| Verification date                               | 2026-10-27                                                                           |
| Source                                          | Local source snapshot V9, identified by its base commit and input fingerprints below |
| Base commit                                     | `b8d023662e4f3796eea73afeaf4f49d9f7a7a517`                                           |
| Windows environment                             | Python 3.12.10 in the project virtual environment                                    |
| Linux environment                               | Python 3.12.16 in a disposable Docker container                                      |
| Persistence for complete suites and image smoke | Disposable SQLite                                                                    |
| Hosted CI for V9                                | Not run                                                                              |
| Published release for V9                        | Not verified                                                                         |

The base commit alone does not identify the tested source: V9 includes local file
contents identified by the input fingerprints. Results apply to that snapshot and
its recorded environments, not automatically to later source changes or a deployment.
Supporting datasets identify narrower verification scopes independently.

## Test and static-analysis results

| Check                                | Result                                                                 |
| ------------------------------------ | ---------------------------------------------------------------------- |
| Windows complete suite               | 765 passed; 96.12% overall coverage with branch measurement            |
| Linux complete suite                 | 765 passed; 96.24% overall coverage with branch measurement            |
| Formatting                           | Black: 125 files unchanged on Windows and Linux                        |
| Lint                                 | Ruff passed on Windows and Linux                                       |
| Application typing                   | mypy: 52 source files passed on Windows and Linux                      |
| Editor typing                        | Strict Pyright: 31 affected Python source/test files; zero diagnostics |
| Core limiter checks                  | 13 focused tests passed on Windows                                     |
| Middleware coverage gate             | 96%; required minimum 90%                                              |
| Lifecycle coverage gate              | 99%; required minimum 95%                                              |
| Database coverage gate               | 100%; required minimum 95%                                             |
| API coverage gate                    | 99%; required minimum 95%                                              |
| Limiter core/store/policy/middleware | 100% statement and branch coverage                                     |

Linux checks use a read-only source mount. Development requirements are installed
only inside the disposable verification container; coverage, caches, and test
databases use `/tmp`. The saved runtime image contains runtime requirements only.

## Verified behavior

| Boundary                  | Evidence                                                                                                                                                                               |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Request deadlines         | Pre-header JSON 408, truncated streams, disconnects, external cancellation, bounded body delivery, delayed cleanup, and suppression of late/duplicate responses                        |
| Request outcomes          | One completed/aborted observation, response-duration timing, concurrent request correlation, final server-error responses, and bounded route/method labels                             |
| HTTP configuration        | Defaults and overrides, strict syntax/types/ranges, relationships, env-source precedence, exact origins, proxy trust, and raw-header/body/method/media policies                        |
| Operational exposure      | Environment defaults, all eight flag combinations, hidden route families/methods/assets/redirects, mounted paths, collector non-execution, per-app isolation, and OpenAPI availability |
| Public probes             | Dependency-free liveness; minimal readiness JSON with correct startup, shutdown, and dependency up/down decisions                                                                      |
| Limiter storage           | Exact rolling boundaries, ring reuse, 20000 same-client rejections, 10000 new-identity capacity rejections, and bounded client/history allocation                                      |
| Limiter admission         | Atomic thread admission, independent clients/instances, active-quota retention, ordered expiry, and capacity recovery                                                                  |
| Limiter HTTP policy       | Distinct 429/503 envelopes, positive remaining-delay retry headers, resolved proxy identity, probe/preflight accounting, early header protection, and favicon GET/HEAD exemption       |
| Socket behavior           | Uvicorn h11/httptools tests for deadlines, streaming/disconnects, configured proxy identity, production exposure, concurrent bursts, capacity, and exact recovery                      |
| Logging privacy           | Console/JSON modes, severity filters, safe diagnostics, ASCII-only streams, bootstrap/fatal/dependency output, and correlated h11/httptools failures                                   |
| Environment documentation | Commented defaults agree with settings; shared env comments match and recorded local overrides are preserved                                                                           |

Contracts and commands are documented in [Testing](testing.md),
[Request deadlines](request-timeouts.md), [HTTP configuration](http-policy.md),
[Operational exposure](operational-exposure.md), [Rate limiting](rate-limiting.md), and
[Logging](logging.md).

## Runtime-image validation

| Field                        | Result                                                                    |
| ---------------------------- | ------------------------------------------------------------------------- |
| Image identity               | `sha256:b7273febd0cf39f7dcf5f3f03f60cf62831a451618e7ef42e189babf2dd7c1dc` |
| Database                     | Disposable SQLite                                                         |
| Network                      | Loopback-only test requests                                               |
| Dependency consistency       | `pip check` passed                                                        |
| Readiness and normal request | HTTP 200                                                                  |
| Production output            | Every record parses as JSON without ANSI styling                          |
| INFO filtering               | Successful access records hidden; lifecycle messages retained             |
| Rejection                    | HTTP 404 with one completed access record; raw path/query value absent    |
| Invalid configuration        | Exit 1 with safe critical JSON and no supplied value or traceback         |
| Cleanup                      | Disposable containers removed                                             |

Image identity is local artifact evidence, not a publication or release attestation.
Operational default/override smoke evidence belongs to V7; quota/capacity smoke
evidence belongs to V8. V9's image smoke covers the behavior listed above.

## Supporting verification datasets

All local datasets below have verification date 2026-10-27. Counts and coverage are
specific to each source snapshot. A narrower runtime check is not a complete Linux
suite. Component evidence does not imply that every check was repeated for V9.

| Dataset | Scope                              | Windows complete suite / coverage | Linux complete suite / coverage   |
| ------- | ---------------------------------- | --------------------------------- | --------------------------------- |
| V1      | Dependencies and runtime isolation | 357; 93.99%                       | 357; 94.15%                       |
| V2      | Request deadlines                  | 393; 94.75%                       | 393; 94.90%                       |
| V3      | Compose and MySQL startup          | 393; 94.76%                       | Compose runtime only              |
| V4      | Published-port validation          | 411; 94.77%                       | Focused runtime checks            |
| V5      | Request outcomes and metrics       | 446; 95.32%                       | 446; 95.47%                       |
| V6      | HTTP configuration                 | 606; 95.77%                       | 606; 95.89%                       |
| V7      | Operational exposure               | 672; 95.99%                       | 672; overall coverage gate passed |
| V8      | Rolling-window rate limiting       | 744; 96.19%                       | 744; 96.31%                       |
| V9      | Logging and diagnostics            | 765; 96.12%                       | 765; 96.24%                       |

### Dependencies and native environment

V1 covers fresh Windows development/runtime installations and a fresh Linux development
installation, with successful dependency consistency checks. Its manifests contain
31 runtime pins and 18 development-only pins; all 49 application/tool pins are unique
and match installed versions. Runtime-only distribution/import checks exclude Black,
Ruff, mypy, pytest, HTTPX, coverage, and test plugins as applicable. Its Linux coverage
gates are middleware 92%, lifecycle 97%, database 100%, and API 99%.

PowerShell activation selects the project Python 3.12.10 executable, imports
FastAPI/SQLAlchemy/pytest, and passes `pip check`. Interpreter selection and activation
are environment checks, not proof that an unrelated shell uses the project interpreter.

### Deadline and editor checks

V2 includes twelve socket cases across h11/httptools and 99% timeout-middleware
coverage. Async streaming cleanup fixtures shield cleanup awaits from AnyIO
cancellation. This evidence does not guarantee arbitrary unshielded cleanup or qualify
WebSocket behavior; the HTTP fixtures disable WebSockets and database lifespan startup.

Separate editor checks report zero strict Pyright diagnostics on three timeout-related
files and 39 focused Windows timeout/socket tests passed. The complete-suite result
in V2 belongs to its listed inputs; focused checks do not replace a complete suite.

### Compose and MySQL startup

V3 covers Compose 5.5.1 with MySQL 8.4.6 and the API's actual local topology:

- Compose configuration and authenticated health-based startup pass.
- Both services reach health; item creation returns 201 and readback preserves its
  name and price 12.34.
- Container/network recreation preserves the item in the retained named volume.
- Test containers/network/volume are removed; developer configuration and data are
  outside the disposable project's scope.

This is startup and local persistence evidence for V3, not MySQL-backed complete-suite,
migration, TLS, backup/restore, or release-pipeline qualification. V4 separately covers
published-port defaults, overrides, strict validation, and Compose environment mapping.

### Remote-check observations

The GitHub ruleset observation dated 2026-10-27 records FastAPI ruleset 25976668 on
main/dev/staging, with structural PR/merge/bypass/deletion/non-fast-forward protections
matching Express ruleset 25689316. FastAPI's required-check list is empty in that
observation; Express requires `Deployment gate`. NestJS rulesets
16198248/16198302/16198404 use `Check`/`Migration Check`, with up-to-date requirements
on main/staging. These are dated observations, not confirmation of present settings.

Hosted Quality run [39889071406](https://github.com/desjjoh/QuickAPI-FastAPI/actions/runs/39889071406),
dated 2026-10-23 at `cfa6bdf27f5cdb4a7190ab17d948f4636ee8bbd5`, reports successful
`static-analysis`, `test-layers (unit)`, `test-layers (integration)`,
`test-layers (e2e)`, `combined-coverage`, and `production-container`. It does not
establish a hosted pass for V9. Required-check administration needs independent
confirmation using [Branch protections](branch-protection.md#required-check-configuration).

## Verification limits

- Hosted CI, release publication, SBOM/provenance, and deployed access restrictions
  are not verified for V9.
- Complete automated suites and production-image smoke use SQLite. Supporting MySQL
  startup evidence does not qualify MySQL failure paths or a release pipeline.
- Migration upgrade/downgrade, database rollback/uncertain-commit outcomes, backup
  restoration, and application-wide shutdown draining are not established by these checks.
- Slow-header/whole-upload receive protection, real ingress trust/direct-port denial,
  and deployment probe behavior require hosting-specific verification.
- Limiting is process-local. Instances, workers, replicas, and restarts do not share
  a persistent global quota.
- Limiter rejections precede CORS and do not carry allow-origin headers. Tests cover
  this HTTP ordering; they do not provide a different browser access policy.
- Logging controls cover application output and standard records routed through its
  handler. External process output and independently installed handlers need separate controls.
- Required-check enforcement and broader security/release requirements are tracked
  in [Backlog](backlog.md). A local pass does not establish remote enforcement.

## Source and artifact fingerprints

Base commits identify source lineage. Input SHA-256 values identify the recorded local
file contents; image SHA-256 values identify local runtime artifacts. None of these
identities alone proves publication or a hosted CI pass.

### V9 verified inputs

| Input                                                       | SHA-256                                                            |
| ----------------------------------------------------------- | ------------------------------------------------------------------ |
| `.env.example`                                              | `d0c840c0f1ba67b429434f7757cc68761012da836c1aa6e32bdeaacf05b8a913` |
| `app/api/system/controllers/system_controller.py`           | `972a0e6487abe219d3f7d39332ed11cc197fe420359e280f2147dca9cf4f73a3` |
| `app/common/handlers/exception_handler.py`                  | `f3f55ecf2a651159ec6fd92acc9718e1db622dff36dcebd47555d893546eef7d` |
| `app/common/handlers/lifecycle_handler.py`                  | `c419887795bc470935b78429f9e18fa7b04e51cd6b1ce9af997e27449e32474e` |
| `app/common/helpers/error_diagnostics.py`                   | `44a2c79a829ea29a9316ca398278424f4226941e165b2fa9a5bc396635ce97c6` |
| `app/common/middleware/rate_limit.py`                       | `a4771f95f9be2ca72e2486d468422e8e77b03a8c3c1355e62ee3da2ddc360852` |
| `app/common/middleware/request_context.py`                  | `4cf802aaf15a4f9c3f71f80fa5dbc8931a3a9e105f7e544b420230c182a250f7` |
| `app/common/middleware/request_logger.py`                   | `e2c9f4eb7cfae7f2da367675498e02f7bcdb7125a7fd18bfd7ae672010d63c31` |
| `app/common/middleware/request_timeout.py`                  | `d4df146e26debbdf08a96043ad0bd0e681013d45ae62c87bb777448c16088e9c` |
| `app/common/store/rate_limit.py`                            | `b07775fd32b716c78355f28e27cd3bc7d23cc4a8e13eec76e84d5cd135fe2b3c` |
| `app/config/application.py`                                 | `ef7a0e319cefd764ef3b7339128fe7febf595e4c33e0b96487c60564525163a8` |
| `app/config/database.py`                                    | `4a06dfc1cd8c8de099223f3483728979ea118144e3b6a7ff7fdd02fad683a62f` |
| `app/config/environment.py`                                 | `9b48ed0c0ded2612e8307a2c25a323c06fc3c0164222c7a5a00ee00b51689b78` |
| `app/config/logging.py`                                     | `f31a2203c81e1c900f2c7ba9716e518db50f26786ae700c007d7d574bfd21759` |
| `app/config/rate_limit_policy.py`                           | `fc7233c555344f47c43875fe7f75f98d9e33c6149f9748ec9993b78f7d3c7f22` |
| `app/config/rate_limiter.py`                                | `c141614ff344a804d8a2900f7e4b49aa0674caf3907c75c7fc79dc01f7964820` |
| `app/main.py`                                               | `7bb4d8ed68f8d02f449d7b0838d74a28bf5b2189e8091ae9124038f9c0e65134` |
| `tests/conftest.py`                                         | `584a0e9a414d735e097a781e3272f4dc2f081a0f125b249dd3e2be206bfa870e` |
| `tests/integration/errors/test_middleware_rejections.py`    | `ee944571570318d8ad4e5e91ff624cf038aba1b52d52a1b15b37f48c0991f192` |
| `tests/integration/middleware/test_application_stack.py`    | `a4e21748b5b794cb00309a89c9c64dddfa86eb2fb3c1e14b9a066d5ba96b5468` |
| `tests/integration/middleware/test_http_policy.py`          | `c8034ac1bb23c54f863c063e3fac3653fb1f40130fbc2f4cd769a7c500de1199` |
| `tests/integration/middleware/test_logging_privacy.py`      | `4e0b89bdd5d67b7662795d281d2765b4e126c91a053e7ad8ca27a5ab41206878` |
| `tests/integration/middleware/test_operational_exposure.py` | `5d22831ec839569ff63ccc124653dda5853ff1280609b7196f5798a8a60ea827` |
| `tests/integration/middleware/test_rate_limiting.py`        | `117d7ec1a4afe2cd7b6f09c343a422e8a95da278d509a2d0623776e652d12ea8` |
| `tests/integration/middleware/test_request_outcomes.py`     | `dfc736adca320f2f97dc04409e9a638aa9e86f62ae3e5f1c625c4b29df110bb6` |
| `tests/unit/config/test_environment.py`                     | `ce8412866d3774972629baba4bf7b17121c0ff3f59e294832fda80ea2f886302` |
| `tests/unit/config/test_logging_privacy.py`                 | `57c6cd42b83585ddf5c0b6b3bb994a53fb5c4036f003a4d324e55640c0b99db5` |
| `tests/unit/config/test_rate_limiter.py`                    | `981fe303f9dfc0f314760b1a0cb01f8165f8116eefb63fd7dbd24d5c700030e0` |
| `tests/unit/middleware/test_rate_limit.py`                  | `00a0abf556bbffd177072aec313afc6657ab1cecc300a74ac4b75cb7e698d79f` |
| `tests/unit/middleware/test_request_logger.py`              | `a5c83450a47c4835132a85a9585968865efb0b6b2ae2ec6b92d72cddff0e6bc0` |
| `tests/unit/middleware/test_request_timeout.py`             | `c334be85f790332bbdc6b973830a058151c65b4ce5d2ec34741147726d9d65a0` |
| `tests/unit/test_database.py`                               | `cd300cae5dd13113102546543016132a42d77656b30794723f86de61b3bde639` |

### Supporting source identities

| Dataset | Base commit                                | Local runtime image SHA-256                                               |
| ------- | ------------------------------------------ | ------------------------------------------------------------------------- |
| V1      | `cfa6bdf27f5cdb4a7190ab17d948f4636ee8bbd5` | `sha256:823da9b4d5b9981a120afe5b1505d6f1c519f8f1d55dc296685cffdbcafd8542` |
| V2      | `45d224253a4907f140944eac36ce9f7d894c9379` | `sha256:393e223f296ac3057a13eaff81a642c7ff168fd55de670c28ab027eade0afed3` |
| V3      | `8b0246a524a979aa902575d9519e025c847819e1` | `sha256:29546e9e6a31939cf88eb9c4668ad1363eba1217bfbfd959083a40fbb63739cc` |
| V4      | `8b0246a524a979aa902575d9519e025c847819e1` | `sha256:655330da7d77d04e0dae467c2003091c9286233a64617b3d5835d7145ed565a9` |
| V5      | `9bc06651d4f9da5fb64df5b4b71f57b04164492b` | `sha256:580017393e8c8ea335f78f32d0270a73d2a06cf44e4978952378df286d9e85f4` |
| V6      | `609e143f1766e4da60f83fc4b011c4e19e3d3664` | `sha256:f0f9f948a0bb2312a8123fb9286528e07074846494ff2a50b0010f98d0738949` |
| V7      | `ccef70096aabc31a9022409d7b25b591a89e3395` | `sha256:bd6e898e5412675caf75323d3581b45e14f025051ed5a3c453bc11ff02655924` |
| V8      | `b8d023662e4f3796eea73afeaf4f49d9f7a7a517` | `sha256:c04f1169674a9a6c085bb53b9891dc98d8d00c46fe0e77a76f9b3c315bbee1c8` |

#### V1 - Dependencies and runtime isolation

| Input                         | SHA-256                                                            |
| ----------------------------- | ------------------------------------------------------------------ |
| `requirements.txt`            | `bbba8ec97d5ece47e096a520f35013ab9de4db6ea1354ded43c466c51efb5be9` |
| `requirements-dev.txt`        | `78e2697eed46117b133a6748bd74d200f60c03c2f7b75d10b08dd12937011140` |
| `Dockerfile`                  | `fc03a29738267aaedb9e314df58aa0503fdcee62d3c38e8c22c4a35c921a9c3b` |
| `.github/workflows/tests.yml` | `a0648f2aa0c16212276d5704a7181c68e962e39fa817460d1d11e21c6b7e6bf9` |

#### V2 - Request deadlines

| Input                                                    | SHA-256                                                            |
| -------------------------------------------------------- | ------------------------------------------------------------------ |
| `app/common/middleware/request_timeout.py`               | `65bebd95db026c1755cf67e59f62b3527b62da12e586038296324d521d1abc81` |
| `tests/unit/middleware/test_request_timeout.py`          | `31b7dacb44efc6cf090546f3acbfa53088077b4ba378f6f0f6ff02c05fa86da4` |
| `tests/integration/middleware/test_timeout_server.py`    | `de9d176e8077d8140bccb6ddb0ad7adf59c3b5b3e731dff43d2b4910e4b1d444` |
| `tests/integration/errors/test_middleware_rejections.py` | `3defe9e357970ffe60fa842decee4d6c03fa7ccac427c68ee95d4133bf162106` |

#### V3 - Compose and MySQL startup

| Input                         | SHA-256                                                            |
| ----------------------------- | ------------------------------------------------------------------ |
| `docker-compose.yaml`         | `4f60c503e1ba4b77f279dc9725c33cee7be94b29f244512147caf8145c7d2809` |
| `.env.example`                | `38f6a8837a1170874034c8bf1b423d183a58706f600f4bd6a5dbda7042bec903` |
| `.github/workflows/tests.yml` | `c7b193844a343478993b5b3589ec12fb5189d9cab4ead27a5b1f4302a2c7d690` |

#### V4 - Published-port validation

| Input                                   | SHA-256                                                            |
| --------------------------------------- | ------------------------------------------------------------------ |
| `app/config/environment.py`             | `dd7f90723c8fa2109b295ab2e66e8e4cab4ac62e5493c1d44dbc30f4bba7e994` |
| `tests/unit/config/test_environment.py` | `02ef5333e269972e306debb879f01adbc331f3c9e25c1cd742b07a44c56ac0e8` |
| `tests/conftest.py`                     | `52ddfdf09c61e487cd08b7c87dec7dbee834af8be25618f69f7184038987252e` |
| `docker-compose.yaml`                   | `9374cd60eabc3f028a40f2456ca429f45d819ffeffe59fa1c0d221f3c0b9da93` |
| `.env.example`                          | `bfa1a4e6ce6097f4e3dd4e1a188c14643d74fc16c31470c569960b8b0628b3c2` |

#### V5 - Request outcomes and metrics

| Input                                                   | SHA-256                                                            |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `app/common/middleware/request_outcome.py`              | `17adf8a617d37fff3e12ef239678307cc5639a0ea38aad4eb66a95f7020c3a9e` |
| `app/common/middleware/request_logger.py`               | `7f0a3f76f745c9e8c6687f7cc4a9258313d98853b82ea38e94aed63ce969842e` |
| `app/common/middleware/prometheus_metrics.py`           | `6e9faacb39e0d67f96f1a2f7766cdeb5286e7943af728d9d751809bcb9ee1ad0` |
| `app/common/middleware/request_timeout.py`              | `beb76b8a496516805dd12cf4dd83c235cf40d644df94599e8344b11932922437` |
| `app/config/application.py`                             | `d14387dede0616addad3ad96d3ac4bda80a794813416be5f992f2574e3705e1f` |
| `app/config/metrics.py`                                 | `972c7263d4ba2ec31450c5eb9b979b9ec2ccf38c6c842e0054f52dc1010ba060` |
| `tests/unit/middleware/test_request_outcome.py`         | `523601512772dc99f50314f7f7eeb8b9b62f122d19214b14bed969cd161b6e75` |
| `tests/integration/middleware/test_request_outcomes.py` | `f9fedd4eae8994c91f57bf85c5c1e47395c385cd89154f7ab54c38a53249ee44` |

#### V6 - HTTP configuration

| Input                                                  | SHA-256                                                            |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| `.env.example`                                         | `32d19da6fa1e8c87a9a3ae7bf62f2f428690344e7eaa326333bf910718653b7b` |
| `app/config/environment.py`                            | `341d1b47c74b0b95df2f5c64c3af0d521fd580ba98a73b5183a9e839205e7579` |
| `app/config/http_policy.py`                            | `3947ff9fa9c0073f98bff2bcff2eb8f86dafb3f75163a9697fe366779dbfc649` |
| `app/config/application.py`                            | `ce7965f4e84b9556d36f8891fa482d514e01ababa88f0d9667c9e980e1f1a40c` |
| `app/main.py`                                          | `5e0d98c466bc82928a3ff8f31e5f81ccc479bd13a07ef7c2ee4da3a7e30f65fb` |
| `app/common/middleware/trusted_proxy.py`               | `644d1e4bf8c6f1c391a5e8a4a7833a0e9840fb00d23c413590c494f782747bdd` |
| `app/common/middleware/cors.py`                        | `33cf0890ddf1813b66da46678dd9b58fb83f5cb09f678a729d6db50e9125a303` |
| `app/common/middleware/request_header_sanitization.py` | `a0bdb19dc643df02bb3ee523f93810dacdfd5450c4c57abcf3dbb5c5d79a8e67` |
| `tests/unit/config/test_environment.py`                | `b59d16c26ebd3493169c45b037290ccc7e0aab7adfaa5e82584297e410e84b00` |
| `tests/unit/middleware/test_trusted_proxy.py`          | `4db073b4bc3229ba887df662e105e051cf77bed4b12d2b9272e548e4f8faff15` |
| `tests/integration/middleware/test_http_policy.py`     | `9ac2209fbf963a456e155a6099eaee280896e1fe098110c1cb6158e758a6eebe` |

#### V7 - Operational exposure

| Input                                                       | SHA-256                                                            |
| ----------------------------------------------------------- | ------------------------------------------------------------------ |
| `.env.example`                                              | `e845da7a0d01635ca6f73e8770d2aacc99dff2c410ea13753363cc7d04fd7b73` |
| `app/config/environment.py`                                 | `4970c48bd8d3c957dfe7acc145615032c8b61f0430be54e0ce09994363e84f9c` |
| `app/config/application.py`                                 | `c739654488adece701949426a0bcca8391b27b14eeb4953b679e3a5960f64f73` |
| `app/api/api_routes.py`                                     | `117b9c1e02028b927834296bdc69ec7e328f5a82ba525c8b3ac9993e697e03d0` |
| `app/api/system/controllers/system_controller.py`           | `72768fe6b4a1b2e7257ed8b88f25c4eada06f9ac8b33ee7c57f7c467cd8ae8bb` |
| `app/api/system/models/ready_model.py`                      | `9ecfb46adea3c8cb4e3318fa917da26ddadf9d378a7fd24226f0fdee5f8c4f01` |
| `app/common/middleware/operational_exposure.py`             | `28939fbcb3b09d073aba0cf04cd6a9ec629b29cc4e0a98154b804cd7be1ea6df` |
| `app/common/middleware/security_headers.py`                 | `b47fd90e1ea0e677aaee3a27db39915bcfa9a09e189d351289cc1df07a2ba83d` |
| `tests/integration/middleware/test_operational_exposure.py` | `4b13e3ebf3368e91f9ff1b5445626da85308bf13b1cf470f7830d19e8ed00472` |
| `tests/unit/config/test_environment.py`                     | `e98308a4f9b0c640aa5249750a8ba3ae9eb3c5214c80870859c63a0e24753335` |
| `tests/integration/errors/test_open_api.py`                 | `ae20d42d48f5cb5e9b5d55203e5e9f5177bbf8ec422f9b66c925b9e4236dc4a2` |

#### V8 - Rolling-window rate limiting

| Input                                                | SHA-256                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------ |
| `.env.example`                                       | `c7661d4c9b2234e3872794938787d60b7b9e885bf5c1c97a477dbd7fd1ec1e41` |
| `app/config/environment.py`                          | `9339dd0205b76b2301d6c718c63ad379d25301130469d48f83bef52bc76dd0e9` |
| `app/config/rate_limit_policy.py`                    | `fc7233c555344f47c43875fe7f75f98d9e33c6149f9748ec9993b78f7d3c7f22` |
| `app/config/rate_limiter.py`                         | `c141614ff344a804d8a2900f7e4b49aa0674caf3907c75c7fc79dc01f7964820` |
| `app/common/store/rate_limit.py`                     | `b07775fd32b716c78355f28e27cd3bc7d23cc4a8e13eec76e84d5cd135fe2b3c` |
| `app/common/middleware/rate_limit.py`                | `a4771f95f9be2ca72e2486d468422e8e77b03a8c3c1355e62ee3da2ddc360852` |
| `app/config/application.py`                          | `fdf39c82d5c1426b98a0e8fc6cd5bb1cd3ee160876d87b2732981d405c77c968` |
| `app/api/system/controllers/system_controller.py`    | `972a0e6487abe219d3f7d39332ed11cc197fe420359e280f2147dca9cf4f73a3` |
| `tests/unit/config/test_rate_limiter.py`             | `981fe303f9dfc0f314760b1a0cb01f8165f8116eefb63fd7dbd24d5c700030e0` |
| `tests/unit/config/test_environment.py`              | `ce8412866d3774972629baba4bf7b17121c0ff3f59e294832fda80ea2f886302` |
| `tests/unit/middleware/test_rate_limit.py`           | `00a0abf556bbffd177072aec313afc6657ab1cecc300a74ac4b75cb7e698d79f` |
| `tests/integration/middleware/test_rate_limiting.py` | `117d7ec1a4afe2cd7b6f09c343a422e8a95da278d509a2d0623776e652d12ea8` |

</details>
