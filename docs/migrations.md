# Database migrations

[Documentation index](../README.md#documentation)

## What migrations do

SQLAlchemy models describe the schema the application expects. Alembic migration
files describe how to create or change that schema. Each revision contains an
`upgrade()` and a `downgrade()`, plus a link to its predecessor. The database's
`alembic_version` table records its applied revision; `head` means the latest
revision in the checked-out application, and `base` means no applied revisions.

The initial revision creates the current `items` table and its name index. IDs,
timestamps, prices, and the HTTP contract retain their existing behavior. The
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
running a write command. Migration commands use the same application settings as
the API; no database URL or credentials are stored in `alembic.ini`.

`upgrade head` may finish without additional output when successful. `current`
should report `0001_create_items (head)` for the initial schema. A nonzero command
exit means failure; resolve it before starting the API. SQLite remains supported:
select a file-backed SQLite URL and run the same migration command before startup.

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
5. Run `python -m black app tests` and `python -m ruff check app tests`; review any
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

## Verification boundaries

Migration integration tests cover the fresh baseline, model comparison, repeated
upgrade with retained data, missing/incompatible history, offline SQL, and a
disposable downgrade/reapply cycle. SQLite tests remain fast local/CI checks;
recorded Docker MySQL smoke evidence is separate from a complete MySQL test suite.
Broader MySQL CI infrastructure, representative future data upgrades, capacity/TLS,
and outage/recovery qualification have their own acceptance criteria in
[Milestones](milestones.md).

The command model follows the [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
and its [async SQLAlchemy integration](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
