# Disposable MySQL testing

[Documentation index](../README.md#documentation)

[Database readiness and recovery](database-lifecycle.md) documents probe deadlines,
shared checks, startup cleanup, and runtime recovery behavior.

## Development and test databases

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

## Run the tests

```powershell
python -m pip install -r requirements-dev.txt
# Start MySQL, wait for authenticated health, migrate, run integration and E2E,
# then remove the disposable container/network even after failure.
python -m scripts.test_db test
```

Run individual layers using the same process as CI:

```powershell
python -m scripts.test_db test --layer integration
python -m scripts.test_db test --layer e2e
```

These runs use MySQL for shared repository/API persistence fixtures. Isolated
SQLite migration and file-disposal checks still use their private temporary files.
The pytest summary reports the selected backend and number of database-backed
tests selected. A MySQL selection with no database-backed tests fails. MySQL
unavailability, failed migrations, failed collection, and failed assertions all
produce nonzero exits; no SQLite fallback or automatic skip is provided.

The normal compatibility suite remains:

```powershell
python -m pytest -q
```

That command uses private SQLite databases unless MySQL selection was explicitly
requested by the wrapper. Unit tests remain independent of Docker. Full-suite
branch coverage is measured by the compatibility run; separate MySQL checks must
also pass in CI.

## Keep the test database for inspection

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

## Test database migration commands

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

### Creating a migration

Normally create and review schema changes against the development database using
the [migration authoring guide](migrations.md#creating-a-schema-change), then apply
the same files to the disposable test database with `migrate` and run tests.

To deliberately generate a proposed revision against the test database instead:

```powershell
python -m scripts.test_db up
python -m scripts.test_db migrate
# Change the SQLAlchemy models before generating the proposal.
python -m scripts.test_db revision --message "describe the schema change"
python -m black app tests scripts
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

### Downgrade or reset

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

## TLS qualification

Generated certificate directories use mode `0755` and their files use `0644` so
the container's MySQL user can read the read-only mount on native Linux, regardless
of the host user's UID. This includes the disposable test key; these permissions
are for ephemeral test credentials, not deployment private keys. The command
removes the generated directory after stopping the TLS container.

`python -m scripts.test_db tls` creates an independent temporary CA/server and MySQL project on loopback port 3312. It verifies encryption, trust/identity rejection, stalled TLS setup cleanup, and the native API entrypoint, then removes those resources. These cases are explicitly deselected from ordinary runs and executed by the MySQL integration CI job. See [Database capacity and transport](database-settings.md) for policy and Windows loop requirements.

## Configuration and safeguards

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

## CI and troubleshooting

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
pool/TLS capacity, database outages, or deployed backup/recovery. See
[Milestones](milestones.md) and [Verification](verification.md) for scope and evidence.
