# Verification report

[Documentation index](../README.md#documentation)

## Hosted security findings and corrections

Inspected [Quality run 41089796696](https://github.com/desjjoh/QuickAPI-FastAPI/actions/runs/41089796696)
at `9adf2b0a8c80b1328ad6539bc42c5483c6ce1fbf` on 2026-10-30. Static analysis,
unit/MySQL suites, TLS and combined coverage passed. The built-image MySQL
qualification step passed, including API replacement/persistence. The overall
run failed in dependency security, image-report validation and the broad
diagnostics upload; this is not a successful security qualification.

Downloaded security artifacts established the causes. Debian package inventory
versions separate epoch/release from upstream version, while vulnerability records
use the full installed version. The corrected validator reconstructs it exactly.
The original image report now validates offline and still blocks its four unique
critical package/advisory pairs. This verifies parsing without suppressing findings.
The root-owned Trivy cache moved to `.cache/trivy/`, outside artifact paths;
production diagnostics now upload only their log. Artifact actions use v6.

The runtime pins are updated to AnyIO 4.14.2 and asyncmy 0.2.17; development
Certifi is updated to 2026.10.23. Upstream asyncmy release notes confirm removal
of the vulnerable dictionary escaping path despite the scan's absent fixed-version
field. With maintainer approval, the pinned Python 3.12.16 base moves to Debian
13 Trixie, whose SQLite/zlib versions resolve the reported Debian 12 findings.
The registry index digest was verified. Both exception registers remain empty.

With updated local pins, 79 focused Windows security/timeout tests and 65 MySQL
repository/transaction tests passed. `pip check`, formatting, Ruff and targeted
mypy passed. No full local suite, TLS run, image build or live rescan was repeated.
Fresh CI must qualify the new base, dependency pins, artifact upload and security
findings; the downloaded old reports do not establish a clean updated candidate.

## Dependency and image security gates

Implemented on 2026-10-30 against `0b24b5d` plus the security changes. Forty-five
focused offline Windows tests passed: severity/runtime/development policy,
exact exception matching and expiry, missing/invalid inventories, wrong image
identity, exported configuration hashes, scanner failure, temporary cleanup,
malformed JSON and unsupported requirement declarations. The combined formatter,
Ruff and targeted mypy checks passed. Strict editor-type checks cover both new
scripts and the policy tests.

No live dependency audit, container build or image scan was run locally. These
are delegated to hosted CI; no claim is made that the current pins or image have
no critical findings. Empty exception registers grant no exemptions. Application
requirements, environment settings and schema are unchanged. The aggregate CI
gate and remote required-check enforcement remain separately tracked.

## Container replacement and persistence

Implemented against `813feb8` plus the working changes on 2026-10-30. Eighteen
focused Windows tests passed, covering replacement ordering, image/container/database
identity guards, cleanup after failures, retained logs and recovery HTTP assertions.
The combined formatter, Ruff and targeted script mypy checks passed; all four
embedded container programs compile. Recovery assertion tests reject lost item
state, changed replay status/bytes, changed collection state and rejected fresh writes.
The actual built-image MySQL replacement exercise is delegated to hosted CI;
no local image build, Linux, TLS or broad application test run was performed.
No application behavior, environment settings or database schema changed.

The maintainer confirmed that hosted CI passed for runtime hardening on
2026-10-30. This confirmation completes 6A; it does not qualify the subsequent
replacement/persistence changes. The earlier local hardening results below
describe the evidence available before that hosted run.

## Runtime container hardening

Checked on Windows with Python 3.12.10 on 2026-10-30 against `8b6b5c5`
plus the runtime-hardening changes. Six focused image-qualification orchestration
tests passed, including configured-root rejection, runtime-check failure cleanup,
and successful check ordering/termination. The combined formatter, Ruff and
targeted mypy checks passed. Both embedded container check programs compile.

The official registry manifest for `python:3.12.16-slim-bookworm` was inspected;
its index digest matches the Dockerfile pin. No image build or Linux container
execution was performed locally. Effective UID/GID, filesystem permissions,
dependency contents, migrations and HTTP/MySQL startup remain pending the
production-container CI job. These local script tests do not establish those
runtime properties. No environment settings or database schema changed.

The following sections retain the earlier idempotency verification snapshot.

## Source and scope

Verified locally on Windows with Python 3.12.10 on 2026-10-30 against base commit
`a684c78fce8502c7709d489b0f44399ff5e4988a` plus the working changes. This report covers durable idempotency
and affected request/transaction infrastructure. Earlier qualification remains in
Git history; it does not establish full-platform qualification of this candidate.

The Python tree digest for all 195 files under `app`, `tests` and `scripts` is
`7dd91a384e6d73c25bd262a4a034258f96ce8143d12e40ce9b87c620f554ae5c`. Hash sorted project-relative POSIX paths followed by a NUL byte,
raw file bytes and another NUL byte. Local environment secrets are excluded.

The frozen reference-vector fixture SHA-256 is
`eccb27738bbdd983a3a4b0802dc499f854b64330312ff3c42dafb559db5c70ae`.

## Results

| Check | Result |
| --- | --- |
| Keyed mutations and affected regressions | 139 passed: shared-domain reuse, replay/conflicts, rollback, migration, OpenAPI, transaction ownership and guarded resets |
| Real transport boundaries | Eight MySQL/HTTP cases passed across focused selections: lock/commit/release acknowledgement loss, timeout/disconnect after commit, and pre-commit rollback |
| Cleanup and environment configuration | 12 focused unit/configuration cases passed; overlapping sweeps, shutdown ownership, failure logging, defaults and combined limits |
| Additional header/startup/repository checks | 30 cases passed across the initial selection and one corrected error-message assertion |
| Final fingerprint hardening | 15 passed: real secret/excluded inputs, exact Decimal precision, normalization, restart replay and another domain |
| Fingerprint compatibility and input declarations | 31 focused Windows checks passed; frozen v1 vectors, raw model normalization, unsupported nested/direct input rejection and supported item/other-domain replay |
| Static checks | Ruff and the combined formatter passed; mypy passed for 83 application/tool files; strict Pyright passed for 25 affected Python files, including explicit editor inference annotations |
| Environment | New policy comments synchronized between `.env.example` and local `.env`; existing local settings preserved except the requested CORS header addition; test configuration isolated |
| Full Windows suite | Not repeated; focused checks selected for changed behavior |
| Linux, TLS, built image and hosted CI | Not run locally; delegated to CI; hosted results remain unverified |

Initial replay failures exposed reserialization of stored bytes and were corrected.
The focused runs were supplemented with targeted checks after final fingerprint
changes. The last Pylance corrections add explicit types without changing behavior;
static checks were used rather than repeating successful test suites.

## Covered guarantees and limits

- All four item mutations accept optional keys. Invalid/duplicate headers return 400; changed input and active claims return 409. No key preserves normal behavior.
- Validated body/path/query inputs determine the fingerprint. Explicit caller scope and stable application/database namespace allow reuse by other domains; authorization dependencies still run before replay.
- Domain writes and prepared successful responses commit atomically. Original status/JSON bytes replay after later item changes/deletion or application reconstruction, without another revision increment.
- Validation/rendering/completion/commit failures roll back claims and mutations. Size limits reject oversized fresh results; lowering the limit does not invalidate an existing valid replay.
- Completion uses database UTC; results expire after 24 hours and replay never extends expiry. Expired keys can execute again. Cleanup is bounded and safe across overlapping instances; quiesce stops new batches and shutdown awaits active work before database teardown.
- Real packet barriers establish commit outcomes independently of HTTP delivery. Uncertain advisory-lock ownership and failed release retire connections; retries reconcile durable results without duplicate mutations.
- Migration upgrade/repeated upgrade/downgrade/reapply preserves domain data. Downgrade drops replay history. Table metadata matches the models.

Only the guarded disposable test database was migrated to `0003_request_idempotency`.
Development data was not reset or migrated. Apply `python -m alembic upgrade head`
before starting the updated development app; the test-target command is
`python -m scripts.test_db migrate`. See [Migrations](migrations.md).

Idempotency does not provide authorization, delivery guarantees or SQL cancellation.
Expired/unkeyed attempts are not protected against duplicate execution. Release,
backup/restore and deployed topology qualification remain separate work.
