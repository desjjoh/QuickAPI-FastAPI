# Database migrations

[Documentation index](../README.md#documentation)

## What migrations do

SQLAlchemy models describe the schema the application expects. Alembic migration
files describe how to create or change that schema. Each revision contains an
`upgrade()` and a `downgrade()`, plus a link to its predecessor. The database's
`alembic_version` table records its applied revision; `head` means the latest
revision in the checked-out application, and `base` means no applied revisions.

The baseline creates `items` with 16-character IDs, timestamps, exact prices and
a name index. Later revisions add item versions and shared durable-response storage
for the [current item contract](api-contracts.md). The
database itself and its MySQL user are created by Docker's MySQL initialization;
Alembic creates the tables inside that database.

Application startup checks that the database revision matches the single migration
head. It does not create tables or apply migrations. Missing, empty, older, newer,
or unknown revision history prevents startup. Matching history is not proof against
manual schema edits; use the schema comparison command below as an additional check.
Do not use `stamp head` to bypass a migration failure.

## Native Python with Docker MySQL

Run commands from the repository root, with the Python 3.12 virtual environment
activated. On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
docker compose up -d --wait mysql
python -m alembic upgrade head
python -m alembic current
python -m app.main
```

The Compose project is `quickapi-fastapi-dev`. MySQL is published on
`127.0.0.1:3310` and owns a separate project volume. The matching native `.env` URL is:

```dotenv
DATABASE_URL=mysql+asyncmy://quickapi:change-me@127.0.0.1:3310/quickapi-fastapi-dev
```

These are local development credentials. Express and NestJS databases are separate.
The API container uses `mysql:3306` instead of the host address. If you override
`MYSQL_PUBLISHED_PORT`, update the native URL to match. Process environment variables
override `.env`; verify that your shell has no stale `DATABASE_URL` override before
running a write command. Migration commands use the shared [database transport policy](database-settings.md), including bounded admission, connection deadlines, TLS, and compatible Windows loop selection. They use the same application settings as
the API; no database URL or credentials are stored in `alembic.ini`.

`upgrade head` may finish without additional output when successful. `current`
should report `0003_request_idempotency (head)`. A nonzero command
exit means failure; resolve it before starting the API. Only MySQL through `mysql+asyncmy` is supported.

## Item revisions

`0002_item_versions` adds unsigned `items.version` with a non-null database default
of 1, initializing existing rows without changing their other fields. Apply it with
`python -m alembic upgrade head` before starting the updated app. For the guarded
disposable test database, use `python -m scripts.test_db migrate` instead.

Downgrading to `0001_create_items` drops only the version column and preserves
other item data. Revision history is lost; reapplying initializes versions to 1.
Do not mix the versioned API and an older writer. Stop the application before
migration or downgrade, and pair the schema with matching application code.
Development data is never reset or migrated automatically.

## Durable response storage

`0003_request_idempotency` creates the shared `request_idempotency` table and expiry
index without changing item data or revisions. Apply pending revisions with
`python -m alembic upgrade head`, or `python -m scripts.test_db migrate` for the
guarded disposable test target. Downgrading to `0002_item_versions` drops replay
history only; reapplying starts with an empty replay table. Stop the API and pair
application/schema versions when upgrading or downgrading.

## Commands and their effects

| Command | Effect |
| --- | --- |
| `python -m alembic current` | Read the database's applied revision. Empty output can mean no revision has been applied. |
| `python -m alembic heads` | Show the latest revisions available in the source; does not inspect database state. |
| `python -m alembic history` | Show the migration chain. |
| `python -m alembic upgrade head` | Apply pending revisions; repeating it at head makes no schema changes. |
| `python -m alembic check` | Compare the connected database with the loaded models; fail if autogeneration would propose changes. |
| `python -m alembic revision --autogenerate -m "add item field"` | Write a proposed migration file from model/database differences; does not apply it. |
| `python -m alembic downgrade -1` | Undo the most recently applied revision; may destroy data. |
| `python -m alembic upgrade head --sql` | Print migration SQL without applying it; review output before sharing because migrations can contain data. |

Schema comparison/autogeneration does not detect every possible change or prove
data compatibility. Rename operations, data backfills, and database-specific
behavior require deliberate review and tests. MySQL DDL must not be assumed to roll
back transactionally after a failed migration.

## Creating a schema change

1. Apply the existing revisions to your disposable development database.
2. Change the SQLAlchemy models.
3. Run `python -m alembic revision --autogenerate -m "describe the schema change"`.
4. Review the new file under `app/database/migrations/versions/`. Confirm its
   predecessor, column definitions, constraints, indexes, and upgrade/downgrade effects.
   Autogeneration can propose destructive drop/create operations for a rename.
5. Run `python -m black app tests scripts` and `python -m ruff check app tests scripts`; review any
   formatting/import corrections in the generated file.
6. Apply it with `python -m alembic upgrade head`, then run `current` and `check`.
7. Add meaningful migration tests, run the relevant suites, and commit the model
   change and migration together. Test supported downgrades only on disposable data.

Do not edit already-applied revisions to represent a new change. Create another
revision. A downgrade can reverse schema operations only to the extent implemented;
it does not restore deleted rows or establish that an older application is compatible.

## Running the entire stack in Docker

```powershell
docker compose up --build -d --wait
docker compose ps -a
docker compose logs migrate
docker compose run --rm migrate python -m alembic current
docker compose run --rm migrate python -m alembic check
```

The one-shot `migrate` service waits for MySQL health and runs `upgrade head`.
The API waits for successful migration completion and then performs its own revision
check. An exited migration container with code 0 is expected. Failure prevents API
startup. Rebuild after changing migration files; the container uses files baked into
the image. Native commands are the intended workflow for generating migration files.

## Stopping and resetting development data

`docker compose stop mysql` stops MySQL while retaining its data. `docker compose down`
removes this project's containers/network and retains the database volume.

For an intentional reset, stop any native FastAPI process first. Confirm the project
is `quickapi-fastapi-dev`, then run the following from this repository:

```powershell
docker compose -p quickapi-fastapi-dev down --volumes
docker compose -p quickapi-fastapi-dev up -d --wait mysql
python -m alembic upgrade head
```

This deletes all data in that Compose project's volume. Do not run the reset against
another project or a shared database. No existing-database adoption or automatic
reset is performed. Initial MySQL credentials and database names apply only when
initializing a fresh volume.

## Disposable test database commands

Development commands above use `.env`. For the independent Docker test database, use `python -m scripts.test_db up`, then `python -m scripts.test_db migrate`. The wrapper explicitly loads `.env.test` and guards the target. [MySQL testing](mysql-testing.md#test-database-migration-commands) documents generation, upgrade, downgrade, and inspection commands; both environments use the same migration files.

## Verification boundaries

### Upgrade and rollback qualification

The migration evidence suite runs through the selected, guarded database fixture:

```powershell
python -m pytest -q tests/integration/database/test_migration_evidence.py --no-cov
python -m scripts.test_db test --layer integration
```

The first command requires the disposable MySQL server to be started and migrated;
the wrapper in the second command manages that setup automatically. The real baseline is downgraded and recreated:
its downgrade drops `items` and destroys rows, rather than restoring old data.

Test-only revisions under `tests/fixtures/migrations/` add a column to disposable
`items`, backfill existing rows, set a default/non-null constraint, create an index,
and reverse the change. Their separate `migration_evidence_version` table keeps
application revision history independent. They are not shipped as application
migrations or included in the runtime image. Tests compare original IDs, names,
prices, nullable descriptions, and timestamps through upgrade/downgrade, and exercise
fresh insertion defaults and reapplication. The additive change is schema-only;
reversing it loses any values held exclusively in that new column.

History checks reject incompatible revisions before lifecycle readiness and permit
startup after restoring the expected revision. Multiple source heads are rejected.
Schema comparison detects the tested missing-index and unexpected-column changes
even when revision history matches. This is not exhaustive drift detection, and
startup deliberately remains a revision check rather than a schema repair operation.

### Application ordering and recovery

The current application requires exact revision equality. Use a stopped-application
sequence: stop the API, apply the intended migrations, inspect `current` and `check`,
then start the matching application and verify readiness. This policy does not
support mixed application revisions during a rolling schema deployment.

To revert application/schema versions, first establish that the target application's
expected revision and data requirements are supported by the proposed downgrade.
Stop the API, execute the reviewed downgrade, inspect the resulting schema/data, and
start that matching application. The current repository has only its initial real
revision; no historical application image rollback is claimed. Every future real
migration needs its own representative-data and compatibility tests. Retained-image
release rollback and backup restoration remain separate verification work.

A deliberately failing test revision creates a table and then raises. On MySQL,
the table remains while the evidence revision stays at its predecessor. A failed
migration therefore requires inspection of both history and physical schema; do
not assume a transaction undid earlier DDL or retry/stamp blindly. The test removes
its known partial artifact explicitly. For an ordinary disposable test-environment
reset, use `python -m scripts.test_db down`, `up`, and `migrate`. For any database
whose data must be retained, recovery needs a reviewed repair/restore procedure;
these disposable tests do not establish one.

Migration integration tests cover the fresh baseline, model comparison, repeated
upgrade with retained data, missing/incompatible history, offline SQL, and a
disposable downgrade/reapply cycle. All database cases use MySQL. Destructive
revision tests hold the exclusive disposable-database guard, start with a blank
schema, and restore the baseline before releasing the guard.
MySQL integration/E2E infrastructure is documented separately. Representative future data upgrades, capacity/TLS,
and outage/recovery qualification have their own acceptance criteria in
[Milestones](milestones.md).

The command model follows the [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
and its [async SQLAlchemy integration](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
