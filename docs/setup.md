# Setup

[Documentation index](../README.md#documentation)

## Prerequisites and native startup

Use Python 3.12 and pip with the committed runtime/development requirement files.
Docker Engine and Compose v2 are required for the default development MySQL,
disposable persistence tests, and image qualification. An external MySQL server
can be used deliberately with a reviewed `DATABASE_URL`.

Run commands from the repository root. PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip check
Copy-Item .env.example .env
# Review .env before starting; never overwrite existing configuration blindly.
docker compose up -d --wait mysql
python -m alembic upgrade head
python -m app.main
```

Bash:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip check
cp .env.example .env
# Review .env before starting.
docker compose up -d --wait mysql
python -m alembic upgrade head
python -m app.main
```

The example native API is `http://localhost:8000`. Development enables reload;
production/test do not. Use `python -m app.main` for the coordinated entrypoint,
signal handling, and shutdown watchdog. Plain Uvicorn invocation does not provide
that complete lifecycle contract. Review [Configuration](configuration.md) before
startup and [Deployment](deployment.md#graceful-shutdown) for shutdown ownership.

## Local Compose

Copy `.env.example` to a gitignored `.env` if one does not exist; otherwise reconcile the example with your existing configuration. Do not overwrite an existing file containing configuration you need.

```sh
# Entire local stack; waits for actual service health.
docker compose up --build -d --wait
# Or run only MySQL and start the API natively with python -m app.main.
docker compose up -d --wait mysql
```

| Connection                                | Address                 |
| ----------------------------------------- | ----------------------- |
| Container API from this machine           | `http://127.0.0.1:8000` |
| Native Python API with example settings   | `http://localhost:8000` |
| MySQL from native Python/database clients | `127.0.0.1:3310`        |
| MySQL from the API container              | `mysql:3306`            |

`API_PUBLISHED_PORT` and `MYSQL_PUBLISHED_PORT` are optional host-port overrides, commented out in `.env.example`. Omitted or empty values use ports 8000 and 3310 respectively; uncomment only when changing them. Settings validation accepts only whole-number ports from 1 through 65535; malformed, fractional, whitespace-only, zero, and out-of-range values fail. Compose forwards its resolved overrides into the API container for validation. Both bind to loopback. The API container explicitly uses `HOST=0.0.0.0`, `PORT=8000`, and `ENV=production` so its built-image process does not enable development reload. Its health check always probes internal port 8000. Native Python uses its configured `PORT` and `ENV` independently.

Compose loads application identity/logging/timezone from `.env`, then overrides `DATABASE_URL` to `mysql+asyncmy://quickapi:change-me@mysql:3306/quickapi-fastapi-dev`. A native `localhost` URL cannot address the separate database container from inside the API. Changing `MYSQL_PUBLISHED_PORT` requires updating the native `DATABASE_URL` too. To use a different external database for containers, deliberately replace the local Compose database configuration; changing only `.env`'s native URL does not override it.

This file is **local development only**. It uses database `quickapi-fastapi-dev`, user `quickapi`, password `change-me`, and root password `local-root-password`. Those are matching, fixed local defaults, not deployment secrets. MySQL health checks authenticate as the application user and execute `SELECT 1` against that database. API startup waits for MySQL health. The one-shot migration service applies Alembic revisions before the API starts. Native Python requires `python -m alembic upgrade head` first.

The default Compose project is `quickapi-fastapi-dev`. Compose project scoping names the containers, network, and `mysql_data` volume; there are no fixed container names that collide with Express/NestJS. The default MySQL host port is 3310, separate from sibling development/test services. Use another published port or `docker compose -p <project>` when needed; project isolation does not by itself change published ports.

```sh
docker compose ps
docker compose logs --tail 100 api mysql
docker compose down
```

`down` removes this project's containers/network and preserves its database volume. Recreating the stack reuses the data. `docker compose down --volumes` also deletes this project's MySQL data; use it only for an intentional local reset. Restart/recreation is not a backup strategy. MySQL initialization credentials apply when a volume is first created; changing Compose values does not rotate users in an existing database.

See [Database migrations](setup.md#database-migrations) for the complete first-run guide, command reference, migration authoring, and intentional reset procedure. The FastAPI database is disposable and separate from shared local databases.

## Interpreter and dependency maintenance

[Formatting](setup.md#formatting-and-readability) defines the shared logical spacing rules, CLI and editor
integration. Run `python -m scripts.format_code` to format Python sources and
`python -m scripts.format_code --check` to run the same check as CI. Format-on-save
uses this combined formatter through the Black Formatter extension.

Pip is the selected package installer. [requirements.txt](../requirements.txt) contains runtime dependencies and manually maintained transitive pins. [requirements-dev.txt](../requirements-dev.txt) includes it and adds formatting, typing, tests, HTTP test clients, and their supporting packages. Local development and CI install the development file; Docker installs only the runtime file. No uv or generated lockfile is required.

After activation, verify `python --version` reports 3.12 and `python -m pip --version` points inside this repository's `.venv`. The Windows launcher may need a new terminal after installing Python. If `py -3.12` cannot find it, use the full path to the installed Python 3.12 executable. An existing virtual environment retains the interpreter used when it was created; installing 3.12 does not convert a 3.14 environment. Preserve or remove the old environment deliberately and create a fresh one with 3.12.

For production or a separate runtime-only verification environment, create another Python 3.12 virtual environment and install only `requirements.txt`, then run `python -m pip check`. Installing the runtime file into an existing development environment does not remove its development tools.

When updating dependencies, edit the appropriate exact pins, reconcile related transitive requirements, and verify fresh runtime and development installations. Run `python -m pip check`, static checks, tests, and the runtime-image checks. Avoid replacing these curated lists with an unreviewed `pip freeze` from a long-lived environment. These files pin application packages, not Python/pip or operating-system packages.

MySQL through `mysql+asyncmy` is the only supported runtime database. Every persistence test uses the separate `quickapi-fastapi-test` project and `.env.test`; unit tests do not open a database connection. See [MySQL testing](testing.md#database-safety) for commands and database boundaries.

## Database migrations

### What migrations do

SQLAlchemy models describe the schema the application expects. Alembic migration
files describe how to create or change that schema. Each revision contains an
`upgrade()` and a `downgrade()`, plus a link to its predecessor. The database's
`alembic_version` table records its applied revision; `head` means the latest
revision in the checked-out application, and `base` means no applied revisions.

The baseline creates `items` with 16-character IDs, timestamps, exact prices and
a name index. Later revisions add item versions and shared durable-response storage
for the [current item contract](architecture.md#api-contracts). The
database itself and its MySQL user are created by Docker's MySQL initialization;
Alembic creates the tables inside that database.

Application startup checks that the database revision matches the single migration
head. It does not create tables or apply migrations. Missing, empty, older, newer,
or unknown revision history prevents startup. Matching history is not proof against
manual schema edits; use the schema comparison command below as an additional check.
Do not use `stamp head` to bypass a migration failure.

### Commands and their effects

| Command                                                         | Effect                                                                                                     |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `python -m alembic current`                                     | Read the database's applied revision. Empty output can mean no revision has been applied.                  |
| `python -m alembic heads`                                       | Show the latest revisions available in the source; does not inspect database state.                        |
| `python -m alembic history`                                     | Show the migration chain.                                                                                  |
| `python -m alembic upgrade head`                                | Apply pending revisions; repeating it at head makes no schema changes.                                     |
| `python -m alembic check`                                       | Compare the connected database with the loaded models; fail if autogeneration would propose changes.       |
| `python -m alembic revision --autogenerate -m "add item field"` | Write a proposed migration file from model/database differences; does not apply it.                        |
| `python -m alembic downgrade -1`                                | Undo the most recently applied revision; may destroy data.                                                 |
| `python -m alembic upgrade head --sql`                          | Print migration SQL without applying it; review output before sharing because migrations can contain data. |

Schema comparison/autogeneration does not detect every possible change or prove
data compatibility. Rename operations, data backfills, and database-specific
behavior require deliberate review and tests. MySQL DDL must not be assumed to roll
back transactionally after a failed migration.

### Creating a schema change

1. Apply the existing revisions to your disposable development database.
2. Change the SQLAlchemy models.
3. Run `python -m alembic revision --autogenerate -m "describe the schema change"`.
4. Review the new file under `app/database/migrations/versions/`. Confirm its
   predecessor, column definitions, constraints, indexes, and upgrade/downgrade effects.
   Autogeneration can propose destructive drop/create operations for a rename.
5. Run `python -m scripts.format_code` and `python -m ruff check app tests scripts`; review any
   formatting/import corrections in the generated file.
6. Apply it with `python -m alembic upgrade head`, then run `current` and `check`.
7. Add meaningful migration tests, run the relevant suites, and commit the model
   change and migration together. Test supported downgrades only on disposable data.

Do not edit already-applied revisions to represent a new change. Create another
revision. A downgrade can reverse schema operations only to the extent implemented;
it does not restore deleted rows or establish that an older application is compatible.

### Running the entire stack in Docker

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

### Stopping and resetting development data

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

## Formatting and readability

### Commands

Activate the Python 3.12 virtual environment and install `requirements-dev.txt`.

```powershell
# Format the application, tests and scripts.
python -m scripts.format_code

# Check the same files without changing them; CI uses this command.
python -m scripts.format_code --check

# Format a specific file or directory.
python -m scripts.format_code app/api/v1/items
```

The formatter combines the pinned Black version with logical blank-line rules.
It reads the project's Black line-length, Python target and string-normalization
settings from `pyproject.toml`. Black handles layout first, logical spacing follows,
and Black runs again to verify a consistent result. Repeated formatting produces
no further changes. Ruff remains the separate import/code-quality check.

### Logical separation

The policy follows the intent of Express and NestJS statement-padding rules while
retaining Python syntax and Black's definition/docstring conventions:

- Keep consecutive assignments together.
- Separate an assignment group from a following operation or guard.
- Separate a completed control-flow block from its next sibling statement.
- Separate `return`, `raise`, `try` and `try*` statements from preceding work.
- Do not add padding before the first statement of a block or after its docstring.

```python
async def get(self, id: HexId) -> ItemORM:
    item = await repo.get_by_id(self.db, id)

    if item is None:
        raise HTTPException(404, f"Resource with ID '{id}' not found")

    return item
```

The checker uses Python statement boundaries, rather than text patterns. It keeps
comments attached to guards/decorators, preserves strings and respects `# fmt: off`,
`# fmt: on` and `# fmt: skip`. A single `raise` inside a guard does not acquire an
extra blank line before it. Compound clauses such as `elif`, `else`, `except` and
`finally` remain attached to their statement.

### Editor integration

The checked-in VS Code settings route the Black Formatter extension through
`scripts/format_code.py`, using the repository's `.venv` interpreter. **Format
Document and format-on-save apply both Black and logical spacing.** Install the
recommended Python, Black Formatter and Ruff extensions. Reload VS Code if an
already-running formatter server has not picked up the changed configuration.

The repository's interpreter settings target Windows. On POSIX, use
`${workspaceFolder}/.venv/bin/python` in both `python.defaultInterpreterPath` and
the first entry of `black-formatter.path`.

Format Selection preserves Black's existing line-range behavior; the full logical
spacing policy runs on document formatting/save. This avoids changing unrelated
statements outside the selected range. The stdin adapter writes only the formatted
buffer to stdout and does not modify the file on disk.

### Scope and enforcement

Default targets are `.py` files under `app`, `tests` and `scripts`, including the
checked-in migration code. Directory discovery skips hidden directories,
environments, caches, build output and `node_modules`; it does not follow symbolic
links. Explicit file/directory arguments let a developer narrow the run.

`--check` exits with 1 for formatting differences. Invalid input or formatting
failure exits with 2. File formatting validates every selected source before writing
changes, preserves its encoding and newline style, and verifies that logical padding
does not alter its syntax tree. Existing valid `# fmt:` exclusions remain available
for deliberate formatting exceptions.

The `Quality / static-analysis` job runs the combined formatter check before Ruff
and mypy. Cramped statements therefore fail CI even when Black alone accepts them.

## Troubleshooting

- Configuration validation names invalid fields before serving requests; correct
  `.env` or supplied environment values and restart.
- Database startup requires the asyncmy driver, reachable MySQL, valid credentials,
  and the current single Alembic revision. Startup never repairs a schema.
- Existing virtual environments retain their original interpreter. If Python 3.12
  is not selected, create a new environment deliberately and reinstall requirements.
- Pytest temporary-directory failures can use a writable disposable
  `--basetemp=.pytest-local-tmp`; pytest may clear that path. See [Testing](testing.md).
- Containers use baked source and Compose overrides. Rebuild after source/migration
  changes; a native `.env` URL does not override Compose's internal database URL.
