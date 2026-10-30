# Verification report

[Documentation index](../README.md#documentation)

## Registry round-trip index correction

Inspected [release run 41127639341](https://github.com/desjjoh/QuickAPI-FastAPI/actions/runs/41127639341)
for `784e5d272a6d2ac99d75c859a1edaea6ff7a2273`. Candidate build, attestation/
MySQL/security qualification and both disposable registry tag digest checks
succeeded. The returned OCI layout failed the original single-root-only check.
Real registry login/publication were skipped; the disposable registry was removed.

The returned-layout validator now selects the independently approved digest and
allows additional catalog entries or consistent aliases. A missing approved digest,
conflicting descriptor, changed blob, wrong runtime/source or invalid attestation
still blocks. Original build archives retain the strict single-root requirement.
The exported catalog is retained as `roundtrip-index.json` for subsequent diagnosis.

Thirty-eight focused offline Windows release tests passed, including returned
catalog/alias fixtures and publisher round-trip coverage. Formatting, Ruff, mypy
and strict editor-type checks passed. A fresh hosted run is required; no local
container build, registry operation or publication was performed. Historical
image rollback qualification remains pending and was not implemented by this fix.

## Verified candidate publication tooling

Implemented on 2026-10-30 against `d7baea1` plus the release changes. The combined
selection passed 84 focused offline Windows cases: 33 release cases and 51
existing aggregate-gate/workflow cases. Release cases cover valid and invalid OCI
content, legacy and OCI artifact attestation binding, source/provenance mismatch,
missing SBOM packages, unsafe archive paths, changed evidence/archives/policy,
stale scans, failed source gates, source attempt selection, version drift,
critical-policy re-evaluation and mocked registry publication/digest preservation.
Both rehearsal and real-publication code paths were exercised with fake tools;
no real registry login occurred. Subsequent focused checks passed for cleanup of
the disposable registry on publication failure, source selection, and OCI artifact
subject storage with inline empty configuration descriptors. Ruff, combined formatting, mypy for
four release modules and strict editor-type checks passed.

The workflow and candidate tooling are implemented; live Buildx attestation
generation, OCI loading, MySQL qualification of this release artifact, Trivy
scanning, disposable registry round-trip and real publication are not yet
qualified. No local container build, live scan, Linux/TLS/full application test
run or registry publication was performed. Hosted validation awaits GitHub
availability and successful main-branch push CI for the exact source commit.
No remote workflow was dispatched, code pushed or image published by this work.
Rollback remains a separate step; hosting verification remains deferred.

## Hosted gate verification and required-check transition

Verified [Quality run 41096725174](https://github.com/desjjoh/QuickAPI-FastAPI/actions/runs/41096725174)
on 2026-10-30 for `5788476ec585ff2ec2e79de51a45757dbbd56eb0`. All eight
job instances passed, including dependency security, both MySQL layers, combined
coverage, production-container and `Deployment gate`. Report upload steps passed;
TLS passed in integration and was intentionally skipped in E2E. The successful
gate's exact context is `Deployment gate`, from GitHub Actions (integration ID
15368). This qualifies the corrected security candidate and aggregate execution.

After the maintainer saved the transition, ruleset 25976668 was re-read on
2026-10-30. It is active for main/dev/staging and requires exactly `Deployment gate`
with integration ID 15368. All six previous individual requirements were removed.
Branch targets, deletion/force-push restrictions, pull-request policy, merge
methods, non-strict update policy and administrator bypass were preserved.
The active ruleset requires that source-bound gate for ordinary PRs; administrator
bypass remains explicit. Hosted all-success execution and offline non-success
gate cases were verified; no deliberately failing hosted PR or merge attempt was
created. No local tests were repeated for this remote/configuration review.

## Aggregate CI gate and retained results

Implemented on 2026-10-30 against `450468c` plus the aggregate-gate changes.
Fifty-one focused offline Windows tests passed, covering explicit all-success,
each required job's failure/cancellation/skip/unknown result, missing and malformed
contexts, unexpected jobs, decision output and workflow structure. Structural
checks require all prerequisite jobs, prohibit continue-on-error, retain both
MySQL matrix entries, and verify triggers plus always-running bounded artifact
uploads. Formatting, Ruff and targeted mypy passed.

JUnit output is added to existing runs; no additional application test run is
introduced. The gate itself uses Python's standard library and does not install
application dependencies. No local MySQL/TLS/image/security scan or full suite
was repeated for this workflow-only change. Hosted aggregate execution and
report uploads remain pending. The GitHub ruleset is unchanged; retain current
individual requirements until hosted gate verification and the separate ruleset
transition are complete. Existing milestone-document formatting edits were
preserved.

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
