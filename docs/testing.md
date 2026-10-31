# Testing

[Documentation index](../README.md#documentation)

## Setup and test boundaries

Use Python 3.12 and install [requirements-dev.txt](../requirements-dev.txt) in the
project virtual environment. Verify `python --version` and `python -m pip check`.
On Windows, activate `.venv\Scripts\Activate.ps1` or invoke
`.venv\Scripts\python.exe` directly. Global Python is not the project's interpreter.

MySQL through `mysql+asyncmy` is the only supported database. All persistence,
migration, pool/session, readiness/recovery, and database-backed process checks use
real disposable MySQL. Unit checks use test doubles and need no running database.

| Layer       | Location             | Boundary                                                                     |
| ----------- | -------------------- | ---------------------------------------------------------------------------- |
| Unit        | `tests/unit/`        | Isolated models, handlers, middleware, configuration and utilities           |
| Integration | `tests/integration/` | MySQL repositories/migrations, application stack, real sockets and processes |
| E2E         | `tests/e2e/`         | Complete application lifespan and HTTP over isolated MySQL persistence       |

Fixtures load `.env.test`, verify live identity, and hold an exclusive reset guard.
Destructive migration cases restore the baseline before releasing that guard.
Development `.env` and the persistent development database are separate.

## Commands

From the repository root with Docker running:

```powershell
# Start authenticated MySQL, migrate, run the full suite with coverage, and clean up.
python -m scripts.test_db test
# Individual persistence layers, without coverage.
python -m scripts.test_db test --layer integration
python -m scripts.test_db test --layer e2e
# Separate generated-certificate MySQL server; cleaned up afterward.
python -m scripts.test_db tls
```

Without Docker, run unit tests only:

```powershell
python -m pytest -q -m unit --no-cov
```

For focused direct pytest checks, use `python -m scripts.test_db up` and
`python -m scripts.test_db migrate` first. Direct `python -m pytest` loads the same
guarded MySQL configuration and fails if the server is unavailable; it does not
start Docker or substitute a different backend. Use `--no-cov` for partial selections
that cannot meet the full application's coverage threshold.

Pytest `.` means passed, `s` means skipped, and `F` means failed. Use `-rs` to show
skip reasons. Windows skips POSIX-only native entrypoint signal cases;
Linux executes them. The MySQL outage case runs on both platforms. Dedicated
TLS cases are explicitly deselected from ordinary runs and run via the TLS command.
Interpret skipped/deselected cases separately from passed checks; counts are not a fixed contract.

## Quality gates

```powershell
python -m scripts.format_code --check
python -m ruff check app tests scripts
python -m mypy app scripts
```

[Python formatting](setup.md#formatting-and-readability) defines logical statement spacing and editor
integration. The combined check includes Black and fails for missing logical blank
lines. Run `python -m scripts.format_code` to apply the same policy locally.

The full MySQL run measures branch coverage and requires 90% overall. CI additionally
requires 90% middleware and 95% lifecycle, database-package, and API coverage. Bash
commands matching CI are:

```bash
python -m scripts.test_db test
shopt -s globstar
coverage report --fail-under=90 app/common/middleware/*.py
coverage report --fail-under=95 app/common/handlers/lifecycle_handler.py
coverage report --fail-under=95 app/database/**/*.py
coverage report --fail-under=95 app/api/**/*.py
```

The shell glob commands require Bash. PowerShell can use
`python -m coverage report --fail-under=95 --include='app/database/*'` for a package.
An unavailable service is a failure to execute the persistence suite, never a pass.

## CI and image qualification

The Quality workflow runs dependency security, static analysis, unit checks, MySQL integration/E2E jobs,
a full MySQL coverage run, built-image MySQL qualification and a Deployment gate. Database jobs own
independent disposable infrastructure. Layer collection must be nonempty; failures
collect bounded logs and cleanup is attempted. Dedicated TLS checks remain in the
MySQL integration job.

[Security](security.md) defines runtime/full requirement auditing and scanning of
the exact image ID passed to container qualification. Critical production/image
findings block; high/medium findings warn and development-only findings remain
nonblocking. Invalid evidence and scanner failures block independently. Offline
Windows regressions use synthetic reports and fake tool runners; live scans run
in CI and retain reports even on failure.

The always-running Deployment gate directly requires all six prerequisite jobs,
including both matrix jobs. It accepts only an explicit `success` result for each;
failed, cancelled, skipped, missing, malformed or unexpected results block it.
Optional steps, such as TLS in the E2E matrix entry, are evaluated through their
owning job's overall result. Cancelling an entire workflow can cancel the gate;
a cancelled or absent gate is not approval and must not satisfy branch protection.

Existing runs emit JUnit XML for unit, MySQL integration/E2E, TLS and combined
coverage selections. CI retains available results, coverage XML/data, bounded
failure logs, image qualification logs, security reports and `ci-gate.json` for
14 days with always-running artifact steps. No scanner cache or image archive
is included. Early tool/setup failures may prevent a report from being produced;
they still fail the job/gate. This adds no application test run.

Triggers include pull requests, protected-branch pushes, merge groups, manual
dispatch and reusable workflow calls. Workflow/gate structural checks run in the
existing unit layer; they do not establish hosted execution or remote enforcement.

```powershell
docker build -t quickapi-fastapi:ci .
python -m scripts.test_image
```

The image command verifies declared and effective non-root identity, code/dependency
permissions, exclusion of development/build tools, explicit migrations, CRUD, probes,
static assets, production exposure defaults, dependencies, and graceful Docker termination against
an independent MySQL server. See [Deployment](deployment.md) for ownership and limits.

It also replaces the API container using the same image, retains the running
MySQL instance, and checks saved item/version state, byte-exact keyed replay,
unchanged collection state and fresh writes after readiness. Both API instances
must terminate cleanly. This does not test MySQL restarts or volume durability.

Required check names and removal of obsolete duplicate contexts are documented in
[Branch protections](testing.md#branch-protection). Workflow definitions and local checks do
not establish hosted success or ruleset enforcement. The aggregate gate must be
verified on GitHub before replacing individual required checks. Representative future migrations, database-volume durability,
backup restoration and candidate-bound release publication remain separately scoped.

## Database safety

### Development and test databases

| Purpose     | Compose project         | Host connection  | Storage                                                     |
| ----------- | ----------------------- | ---------------- | ----------------------------------------------------------- |
| Development | `quickapi-fastapi-dev`  | `127.0.0.1:3310` | Named volume, retained across restarts                      |
| Tests       | `quickapi-fastapi-test` | `127.0.0.1:3311` | Temporary MySQL storage, discarded when the container stops |

Both use MySQL 8.4.6. The test project uses `docker-compose.test.yml` and the
committed `.env.test`, with dedicated local-only credentials. These are disposable
infrastructure credentials, not deployment secrets. Normal API startup uses `.env`;
the test wrapper explicitly selects the test connection and never falls back to the
development `DATABASE_URL`.

Use Python 3.12 with the project virtual environment activated. Run commands from
the repository root. Docker must be running. Development MySQL can remain running
while tests execute.

### Keep the test database for inspection

```powershell
python -m scripts.test_db test --keep-db
python -m scripts.test_db current
python -m scripts.test_db check
python -m scripts.test_db logs
python -m scripts.test_db down
```

`--keep-db` retains the disposable service after success or failure. Application
rows are cleaned between database-backed tests, including assertion failures;
retaining the service does not promise that a failed test's rows remain available.
Migration history is preserved during row cleanup. `down` removes only the fixed
test Compose project. Stopping/recreating its MySQL container discards its temporary
data; do not store development work there.

### Test database migration commands

The wrapper loads `.env.test`, validates the target, verifies its live database/user,
and uses the same checked-in Alembic migration files as development and deployment.
There is no separate test migration chain.

```powershell
python -m scripts.test_db up
python -m scripts.test_db migrate
python -m scripts.test_db current
python -m scripts.test_db heads
python -m scripts.test_db history
python -m scripts.test_db check
```

`up` starts infrastructure only. `migrate` applies pending revisions through `head`.
`current` reads the applied revision; `heads`/`history` inspect source revisions.
`check` compares the connected schema with the models. Do not use `stamp head` to
bypass a mismatch. A normal `test` run applies pending migrations automatically
before tests; direct MySQL fixture use requires a current revision.

#### Creating a migration

Normally create and review schema changes against the development database using
the [migration authoring guide](setup.md#database-migrations), then apply
the same files to the disposable test database with `migrate` and run tests.

To deliberately generate a proposed revision against the test database instead:

```powershell
python -m scripts.test_db up
python -m scripts.test_db migrate
# Change the SQLAlchemy models before generating the proposal.
python -m scripts.test_db revision --message "describe the schema change"
python -m scripts.format_code
python -m ruff check app tests scripts
# Review upgrade/downgrade operations before applying them.
python -m scripts.test_db migrate
python -m scripts.test_db check
python -m scripts.test_db test
```

Generation writes a revision under `app/database/migrations/versions/`; it does not
apply it. Review the file, add appropriate migration tests, and commit it with the
model changes. Autogeneration does not reliably infer renames, data backfills, or
application compatibility. Avoid generating empty revisions when models have not
changed.

#### Downgrade or reset

For a deliberate disposable downgrade/reapply check:

```powershell
python -m scripts.test_db downgrade --revision=-1
python -m scripts.test_db migrate
```

The initial revision's downgrade drops `items`, losing its rows. A downgrade is not
a data restore or proof that an older app can use the schema. MySQL DDL cannot be
assumed to roll back transactionally after failure.

For a fresh test instance:

```powershell
python -m scripts.test_db down
python -m scripts.test_db up
python -m scripts.test_db migrate
```

### TLS qualification

Generated certificate directories use mode `0755` and their files use `0644` so
the container's MySQL user can read the read-only mount on native Linux, regardless
of the host user's UID. This includes the disposable test key; these permissions
are for ephemeral test credentials, not deployment private keys. The command
removes the generated directory after stopping the TLS container.

`python -m scripts.test_db tls` creates an independent temporary CA/server and MySQL project on loopback port 3312. It verifies encryption, trust/identity rejection, stalled TLS setup cleanup, and the native API entrypoint, then removes those resources. These cases are explicitly deselected from ordinary runs and executed by the MySQL integration CI job. See [Database capacity and transport](configuration.md#database-capacity-and-tls) for policy and Windows loop requirements.

### Configuration and safeguards

`.env.test` is the explicit base. Process `TEST_*`, `DB_*` variables and `ENV` can override
it; an inherited production/development `ENV` is rejected. The ordinary
`DATABASE_URL` is ignored as a test target. Required checks include:

- `ENV=test` and literal `TEST_DB_ENABLED=true`.
- A database named `quickapi_fastapi_disposable_test`, optionally followed by an
  underscore and an alphanumeric isolation suffix; development/sibling/system names
  do not qualify.
- User `quickapi_fastapi_test`, with a matching URL, password, and numeric test port.
- A local/test host (`127.0.0.1`, `localhost`, `::1`, `mysql-test`, `mysql-tls-test`), or an exact host
  explicitly listed in `TEST_DB_ALLOWED_HOSTS`. Driver query options are rejected.
- Matching engine URL and live `DATABASE()` / `CURRENT_USER()` before admission;
  live identity is rechecked before row deletion.

To change the local test port, update both `TEST_MYSQL_PORT` and the port in
`TEST_DATABASE_URL`. Native access uses the published host port; a container-side
connection must explicitly use its own host/port configuration. Credentials/name
changes require a fresh test instance. Do not repoint the disposable configuration
to an ordinary database.

Database-writing tests run serially and use real commits. A MySQL advisory lock is
held across each fixture's setup, test, and cleanup. Migration commands acquire the
same lock. A process lock prevents overlapping local wrapper commands from tearing
down each other's Docker infrastructure. Competing commands fail rather than reset
an active target. pytest-xdist workers are rejected. Raw Docker commands bypass the
wrapper safeguards; use the documented wrapper for normal work.

### CI and troubleshooting

The Quality workflow runs `mysql-tests (integration)` and `mysql-tests (e2e)` on
separate runners. Combined coverage and the existing production-container job depend
on their success. Failed MySQL jobs capture bounded container logs as artifacts and
always attempt cleanup. Add these check names to branch protection after confirming
their actual hosted runs; local results do not establish GitHub enforcement.

If a command fails, check Docker availability, `logs`, test-port availability,
configuration safety, and `current`/`check`. Driver failures use a fixed diagnostic
instead of printing credentials or raw SQL. Configuration rejection identifies the
violated guard without echoing connection secrets. A lock failure means another
test/command owns the target; let that work finish before retrying.

These suites establish application persistence behavior on disposable MySQL. They
do not qualify representative future backfills, production-image MySQL smoke,
all pool/TLS faults, all database outages, or deployed backup/recovery. See

## Regression boundaries

### Regression coverage

The manual [retained-image rollback check](deployment.md#releases-and-rollback)
uses an isolated MySQL project and two published digests. Offline Windows checks
in `tests/unit/config/test_rollback.py` cover reference/schema rejection, transition
ordering, retained-state/replay assertions and cleanup failures. Actual image
rollback requires a hosted run with two compatible retained releases.

[Release qualification](deployment.md#releases-and-rollback) builds one source-bound candidate and reuses
the MySQL image checks plus critical-only scanner policy before publication.
`tests/unit/config/test_release.py` tests source/OCI/evidence/publication failure
boundaries offline on Windows. Live release builds, attestations, scans and the
disposable registry round-trip run in the release workflow, including dry-runs.

Place tests at the boundary that owns the behavior. Record source identity,
environment, passed/failed/skipped outcomes, and limitations with the change or
release. Historical executions do not define the current supported configuration.

### Mutation expiry and uncertain outcomes

`python -m pytest -q tests/integration/database/test_mutation_expiry.py --no-cov`
requires the started, migrated disposable MySQL server. It uses real HTTP sockets,
separate observer sessions and a test-owned MySQL packet relay to distinguish
pre-commit rollback, lost acknowledgement, and committed data without a delivered
success response. Checks include disconnect/server cancellation, caught
cancellation, expired acquisition, cleanup failure, invalidation and pool recovery.
Rollback-command and acknowledgement loss verify retirement of the broken lease,
unchanged data, disappearance of the server session, and recovery of a queued caller.
The [shutdown process checks](deployment.md#graceful-shutdown) exercise expired marked
transactions during graceful termination and forced termination of stuck work.
The regular MySQL integration job and full-suite wrapper include these tests.
See [Mutation transactions](architecture.md#mutation-transactions) for limits.

## Branch protection

The checked-in `Quality` workflow runs for main/dev/staging pull requests and
pushes, merge groups, manual dispatch, and reusable calls. Its always-running
`Deployment gate` requires explicit success from every prerequisite, including
security and production-container qualification; skipped/cancelled/missing work
is not approval. Require that aggregate from GitHub Actions for the candidate SHA.

Saved rulesets are GitHub settings. Inspect them before changing required checks,
preserve intended branch/PR and administrator-bypass policy, and verify saved
settings and actual candidate results. Workflow definitions or local test success
do not establish live enforcement.

The intended ruleset targets main/dev/staging, restricts deletion and non-fast-forward
pushes, and requires PRs plus the GitHub Actions `Deployment gate`. It permits merge,
squash, and rebase; requires zero approving reviews; does not require code-owner or
last-push approval, stale-review dismissal, conversation resolution, or up-to-date
branches; and explicitly allows administrator bypass. Confirm saved settings rather
than inferring enforcement from this document.
