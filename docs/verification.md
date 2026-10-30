# Verification report

[Documentation index](../README.md#documentation)

## Source and scope

Verified locally on Windows with Python 3.12.10 on 2026-10-30 against base commit
`cee25c794aa102bbb05307f8dbe3c4b9d635819f` plus the working changes.
This report covers the versioned item contract, lifecycle log alignment and flexible routing. Earlier full-platform evidence is
retained in Git history and does not establish qualification of this candidate.

The Python tree digest for all 182 files under `app`, `tests` and `scripts` is
`6d7657e73822bd054e09140ed7f238a9b486fb951c8a2d0b54efa4c27b552b77`. Hash sorted project-relative POSIX paths followed by a NUL byte,
raw file bytes and another NUL byte. Local environment secrets are excluded.

## Results

| Check | Result |
| --- | --- |
| Existing affected item regression | 371 selected cases passed across the initial run and targeted corrections; initial failures were three outdated response/schema/precondition fixtures |
| Focused concurrency, migration, SQL preconditions, rollback and expiry | 118 passed, including the corrected fixtures; guarded disposable MySQL only |
| Final revision-model and OpenAPI checks | 28 passed |
| Formatting and lint | Combined formatter and Ruff passed |
| Types | mypy passed for 77 application/tool files; strict Pyright passed for 28 affected Python files |
| Lifecycle logging | 26 focused checks passed; two real Windows process checks passed for clean shutdown and cleanup failure |
| Flexible routing | 41 focused Windows checks passed, including three MySQL-backed cases; nested inclusion, root handling, models/dependencies, canonical OpenAPI, system exposure and both mutation spellings covered |
| Documentation | Relative links and code fences checked; migration and client changes documented |
| Full Windows suite | Not repeated; focused checks selected for the changed contract |
| Linux, TLS and built-image qualification | Not run locally; delegated to CI; image smoke inputs updated for versioned mutations |
| Hosted CI / branch enforcement | Not verified for this candidate |

## Covered behavior

- New and existing items start at version 1; response models expose the revision.
- Missing, boolean, string, null, fractional and out-of-range preconditions are rejected. Parsed numeric `1.0` follows Express's integer-number semantics.
- PATCH requires an editable field. PATCH/PUT increment once even for unchanged values; stale retries conflict. PUT omission still clears description.
- Concurrent PATCH/PATCH, PUT/PATCH, update/delete and delete/delete requests use separate sessions behind a held MySQL row lock. One succeeds; the other sees the resulting stale revision or missing resource.
- Direct repository calls with stale preconditions are rejected by SQL without relying on the service's check. Maximum revision blocks further updates but permits deletion.
- POST deletion returns the final persisted representation; repeated deletion returns 404. The previous DELETE route is absent. Canonical collection routes and trailing-slash aliases work without redirects.
- Existing controller/serialization/commit failures roll back field changes and revision increments. Timeout/disconnect tests still reach real writes before verifying settlement and rollback.
- The additive migration initializes existing rows, repeated upgrade preserves revisions, and downgrade preserves other item data. Reapplying after downgrade resets revisions to 1. Metadata comparison, migration history/drift and real online commands pass.

## Lifecycle message conventions

Startup/service timing messages follow the inspected Express/NestJS conventions,
with native Python levels and runtime/service identity. The supported entrypoint
announces HTTP readiness after listener startup. Signal initiation is named and
logged once before draining; programmatic/lifespan cleanup uses requested-stop
wording. The redundant services-stopped record is removed; clean completion uses
`Application exited (code 0)`. Failure paths do not receive that success record.
Log-dependent image/process assertions were updated; image qualification stays in CI.

## Operational boundaries

Only the guarded disposable test database was migrated. Development data was not
reset or migrated. Apply `python -m alembic upgrade head` to the configured development
database before starting the updated app; see [Migrations](migrations.md).

Downgrade loses revision history and requires matching application code. It does
not establish backup restoration or historical-image rollback. Do not mix old
writers with the versioned API. Request timeout or a lost commit acknowledgement
still cannot establish rollback; see [Mutation transactions](transactions.md).
Durable idempotency and replay protection remain separate work.
