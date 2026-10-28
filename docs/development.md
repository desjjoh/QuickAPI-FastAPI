# Development

[Documentation index](../README.md#documentation)

## Prerequisites and startup

Use Python 3.12, matching CI and the container runtime. Run commands from the repository root. The checked-in Compose topology supplies local MySQL 8.4.6 and an optional API container. For native Python, start MySQL first with `docker compose up -d --wait mysql`, then use the example database URL at `127.0.0.1:3308`. An external MySQL instance or local SQLite remains an option.

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip check
Copy-Item .env.example .env
# Edit .env before starting the app.
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
# Or run only MySQL while starting the API natively on port 5000.
docker compose up -d --wait mysql
```

| Connection | Address |
| --- | --- |
| Container API from this machine | `http://127.0.0.1:8000` |
| Native Python API with example settings | `http://localhost:8000` |
| MySQL from native Python/database clients | `127.0.0.1:3308` |
| MySQL from the API container | `mysql:3306` |

`API_PUBLISHED_PORT` and `MYSQL_PUBLISHED_PORT` are optional host-port overrides, commented out in `.env.example`. Omitted or empty values use ports 8000 and 3308 respectively; uncomment only when changing them. Settings validation accepts only whole-number ports from 1 through 65535; malformed, fractional, whitespace-only, zero, and out-of-range values fail. Compose forwards its resolved overrides into the API container for validation. Both bind to loopback. The API container explicitly uses `HOST=0.0.0.0`, `PORT=8000`, and `ENV=production` so its built-image process does not enable development reload. Its health check always probes internal port 8000. Native Python uses its configured `PORT` and `ENV` independently.

Compose loads application identity/logging/timezone from `.env`, then overrides `DATABASE_URL` to `mysql+asyncmy://quickapi:change-me@mysql:3306/quickapi`. A native `localhost` URL cannot address the separate database container from inside the API. Changing `MYSQL_PUBLISHED_PORT` requires updating the native `DATABASE_URL` too. To use a different external database for containers, deliberately replace the local Compose database configuration; changing only `.env`'s native URL does not override it.

This file is **local development only**. It uses database `quickapi`, user `quickapi`, password `change-me`, and root password `local-root-password`. Those are matching, fixed local defaults, not deployment secrets. MySQL health checks authenticate as the application user and execute `SELECT 1` against that database. API startup waits for MySQL health. Schema creation still uses `create_all()`; migrations are later work.

Compose project scoping names the containers, network, and `mysql_data` volume; there are no fixed container names that collide with Express/NestJS. The default MySQL host port differs from their usual 3307. Use another published port or `docker compose -p <project>` when needed; project isolation does not by itself change published ports.

```sh
docker compose ps
docker compose logs --tail 100 api mysql
docker compose down
```

`down` removes this project's containers/network and preserves its database volume. Recreating the stack reuses the data. `docker compose down --volumes` also deletes this project's MySQL data; use it only for an intentional local reset. Restart/recreation is not a backup strategy. MySQL initialization credentials apply when a volume is first created; changing Compose values does not rotate users in an existing database.

## Interpreter and dependency maintenance

Pip is the selected package installer. [requirements.txt](../requirements.txt) contains runtime dependencies and manually maintained transitive pins. [requirements-dev.txt](../requirements-dev.txt) includes it and adds formatting, typing, tests, HTTP test clients, and their supporting packages. Local development and CI install the development file; Docker installs only the runtime file. No uv or generated lockfile is required.

After activation, verify `python --version` reports 3.12 and `python -m pip --version` points inside this repository's `.venv`. The Windows launcher may need a new terminal after installing Python. If `py -3.12` cannot find it, use the full path to the installed Python 3.12 executable. An existing virtual environment retains the interpreter used when it was created; installing 3.12 does not convert a 3.14 environment. Preserve or remove the old environment deliberately and create a fresh one with 3.12.

For production or a separate runtime-only verification environment, create another Python 3.12 virtual environment and install only `requirements.txt`, then run `python -m pip check`. Installing the runtime file into an existing development environment does not remove its development tools.

When updating dependencies, edit the appropriate exact pins, reconcile related transitive requirements, and verify fresh runtime and development installations. Run `python -m pip check`, static checks, tests, and the runtime-image checks. Avoid replacing these curated lists with an unreviewed `pip freeze` from a long-lived environment. Existing package versions were retained during the split; coverage's previously implicit version is now explicitly pinned. These files pin application packages, not Python/pip or operating-system packages.

SQLite remains a supported local runtime option, so `aiosqlite` stays in runtime requirements. MySQL production-like verification is a later phase.

## Configuration

Copy the example, then change values for the target environment:

```bash
cp .env.example .env
```

| Variable       | Requirement                                             |
| -------------- | ------------------------------------------------------- |
| `APP_NAME`     | Non-empty, at most 120 characters.                      |
| `APP_VERSION`  | Three-part semantic version such as `1.0.0`.            |
| `ENV`          | `development`, `test`, or `production`.                 |
| `LOG_LEVEL`    | `DEBUG`, `INFO`, `WARN`, or `ERROR`.                    |
| `HOST`         | Bind address; defaults to `0.0.0.0`.                    |
| `PORT`         | Integer from 1 through 65535.                           |
| `API_PUBLISHED_PORT` | Optional host API port, 1-65535; missing/empty defaults to 8000. |
| `MYSQL_PUBLISHED_PORT` | Optional host MySQL port, 1-65535; missing/empty defaults to 3308. |
| `TIMEZONE`     | Valid IANA identifier; defaults to `Etc/UTC`.           |
| `DATABASE_URL` | SQLAlchemy async URL; MySQL uses `mysql+asyncmy://...`. |

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

Startup creates missing tables but does not migrate existing schemas; see [Architecture](architecture.md#persistence-and-migrations). Quality commands and fixture isolation are documented in [Testing](testing.md).


## Operational endpoint overrides

[Exposure controls](operational-exposure.md) default docs/diagnostics/metrics on in
development/test and off in production. Commented `DOCS_ENABLED=false`,
`DIAGNOSTICS_ENABLED=false`, and `METRICS_ENABLED=false` examples show production
defaults; leave them commented to retain environment-dependent defaults. Compose
runs the API in production mode, so explicit local overrides are needed for container
docs/diagnostics/metrics. Keep these variables/comments synchronized with `.env.example`.
Public liveness/readiness remain available; readiness never includes dependency details.
