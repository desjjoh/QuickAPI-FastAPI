# Development

[Documentation index](../README.md#documentation)

## Prerequisites and startup

Use Python 3.12, matching CI and the container runtime. Run commands from the repository root. The checked-in Compose topology supplies local MySQL 8.4.6 and an optional API container. For native Python, start MySQL first with `docker compose up -d --wait mysql`, apply migrations with `python -m alembic upgrade head`, then use the example database URL at `127.0.0.1:3310`. An external MySQL instance or local SQLite remains an option.

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip check
Copy-Item .env.example .env
# Edit .env before starting the app.
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
# Edit .env before starting the app.
python -m app.main
```

For a self-contained local run set `DATABASE_URL=sqlite+aiosqlite:///./app.db` in `.env`. Relative SQLite paths resolve from the working directory. For external MySQL, replace the URL/credentials and verify that the database exists and is reachable. For Compose MySQL, the local credentials below are already configured; existing `.env` files are not rewritten automatically.

## HTTP environment overrides

[HTTP configuration](http-policy.md) lists validated defaults, ranges, and precedence.
Optional overrides are commented out in `.env.example`; leave them commented to use
code defaults. Process environment wins over `.env`. Lists are comma-separated and
booleans use `true`/`false`. The browser-origin default is `http://localhost:3000`;
configure `CORS_ORIGINS` for another frontend port. Keep shared comments and new
variables synchronized when reconciling an existing local `.env`.

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

See [Database migrations](migrations.md) for the complete first-run guide, command reference, migration authoring, and intentional reset procedure. The FastAPI database is disposable and separate from shared local databases.

## Database capacity and TLS

[Database settings](database-settings.md) defines validated connection/queue/deadline overrides and verified TLS. The same transport factory serves native/container API startup and Alembic commands. Local MySQL remains plaintext by default.

## Disposable MySQL tests

Use `python -m scripts.test_db test` to start, migrate, test, and remove the isolated MySQL test instance on port 3311. Development MySQL on 3310 remains available. [MySQL testing](mysql-testing.md) includes the `.env.test` settings, per-layer commands, test migration generation/application, and intentional reset procedure.

## Interpreter and dependency maintenance

Pip is the selected package installer. [requirements.txt](../requirements.txt) contains runtime dependencies and manually maintained transitive pins. [requirements-dev.txt](../requirements-dev.txt) includes it and adds formatting, typing, tests, HTTP test clients, and their supporting packages. Local development and CI install the development file; Docker installs only the runtime file. No uv or generated lockfile is required.

After activation, verify `python --version` reports 3.12 and `python -m pip --version` points inside this repository's `.venv`. The Windows launcher may need a new terminal after installing Python. If `py -3.12` cannot find it, use the full path to the installed Python 3.12 executable. An existing virtual environment retains the interpreter used when it was created; installing 3.12 does not convert a 3.14 environment. Preserve or remove the old environment deliberately and create a fresh one with 3.12.

For production or a separate runtime-only verification environment, create another Python 3.12 virtual environment and install only `requirements.txt`, then run `python -m pip check`. Installing the runtime file into an existing development environment does not remove its development tools.

When updating dependencies, edit the appropriate exact pins, reconcile related transitive requirements, and verify fresh runtime and development installations. Run `python -m pip check`, static checks, tests, and the runtime-image checks. Avoid replacing these curated lists with an unreviewed `pip freeze` from a long-lived environment. These files pin application packages, not Python/pip or operating-system packages.

SQLite is a supported local runtime option; `aiosqlite` is a runtime dependency. The default suite uses SQLite; explicit MySQL integration/E2E runs use the separate `quickapi-fastapi-test` project and `.env.test`. See [MySQL testing](mysql-testing.md) for commands and database boundaries.

## Configuration

Copy the example, then change values for the target environment:

```bash
cp .env.example .env
```

| Variable               | Requirement                                                                  |
| ---------------------- | ---------------------------------------------------------------------------- |
| `APP_NAME`             | Non-empty, at most 120 characters.                                           |
| `APP_VERSION`          | Three-part semantic version such as `1.0.0`.                                 |
| `ENV`                  | `development`, `test`, or `production`.                                      |
| `LOG_LEVEL`            | `DEBUG`, `INFO`, `WARN`, or `ERROR`; default INFO hides successful requests. |
| `HOST`                 | Bind address; defaults to `0.0.0.0`.                                         |
| `PORT`                 | Integer from 1 through 65535.                                                |
| `API_PUBLISHED_PORT`   | Optional host API port, 1-65535; missing/empty defaults to 8000.             |
| `MYSQL_PUBLISHED_PORT` | Optional host MySQL port, 1-65535; missing/empty defaults to 3310.           |
| `TIMEZONE`             | Valid IANA identifier; defaults to `Etc/UTC`.                                |
| `DATABASE_URL`         | SQLAlchemy async URL; MySQL uses `mysql+asyncmy://...`.                      |

Pydantic validates configuration while importing the application. Missing or invalid
required values produce a field-by-field diagnostic and a non-zero exit rather than
starting a partially configured server. `.env` is for local development; deployment
systems should inject secrets and configuration instead of baking them into images.

## Runtime behavior and troubleshooting

The example uses port 8000 and `ENV=development`, which enables Uvicorn reload. Test/production modes disable reload. Open `http://localhost:8000/docs`, `/redoc`, or `/openapi.json` when `DOCS_ENABLED` is enabled. The versioned collection is `/api/v1/items/`.

`DEBUG`, `WORKERS`, and `METRICS_API_KEY` are not consumed settings. Setting a metrics key does not protect `/metrics`. [Settings validation](../app/config/environment.py) is the source of truth.

- Validation exits before serving requests: fix the named fields in `.env` or injected environment values.
- Database startup fails: check the async URL/driver, reachability, credentials, and schema permissions.
- Pytest cannot create temporary directories: use a writable disposable path with `python -m pytest -q --basetemp=.pytest-local-tmp`. Pytest may clear that directory; never choose a path containing needed data.
- Container configuration differs from local startup: `.env` is excluded from the image. Follow [Deployment](deployment.md).

Startup checks the Alembic revision and does not create or migrate tables; apply revisions first using [Migrations](migrations.md). Quality commands and fixture isolation are documented in [Testing](testing.md).

## Operational endpoint overrides

[Exposure controls](operational-exposure.md) default docs/diagnostics/metrics on in
development/test and off in production. Commented `DOCS_ENABLED=false`,
`DIAGNOSTICS_ENABLED=false`, and `METRICS_ENABLED=false` examples show production
defaults; leave them commented to retain environment-dependent defaults. Compose
runs the API in production mode, so explicit local overrides are needed for container
docs/diagnostics/metrics. Keep these variables/comments synchronized with `.env.example`.
Public liveness/readiness remain available; readiness never includes dependency details.

## Rate-limit overrides

[Bounded rate limiting](rate-limiting.md) defaults to `RATE_LIMIT_WINDOW_MS=60000`,
`RATE_LIMIT_MAX=200`, and `RATE_LIMIT_MAX_CLIENTS=10000`. Optional assignments are
commented in both env files; leave them commented to use code defaults. Requests and
client-capacity settings must also respect their combined two-million-slot bound.
Probes/preflights share quota, so reducing limits can affect local tools and health
checks. Favicon GET/HEAD remains exempt. Stores reset on application restart and
are independent across workers.

## Logging configuration

[Logging](logging.md) uses readable console output in development/test and UTC JSON
in production. Successful request access logs use DEBUG; INFO retains lifecycle
messages and hides successful requests. Both `.env.example` and local override files
should carry the same shared comments. No output-format override is required.
Configuration diagnostics identify fields without printing their supplied values.
