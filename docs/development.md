# Development

[Documentation index](../README.md#documentation)

## Prerequisites and startup

Use Python 3.12, matching CI and the container runtime. Run commands from the repository root. The example database is external MySQL; this repo does not start a MySQL service for you.

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

For a self-contained local run set `DATABASE_URL=sqlite+aiosqlite:///./app.db` in `.env`. Relative SQLite paths resolve from the working directory. For MySQL, replace the example credentials and verify that the database exists and is reachable.

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
| `TIMEZONE`     | Valid IANA identifier; defaults to `Etc/UTC`.           |
| `DATABASE_URL` | SQLAlchemy async URL; MySQL uses `mysql+asyncmy://...`. |

Pydantic validates configuration while importing the application. Missing or invalid
required values produce a field-by-field diagnostic and a non-zero exit rather than
starting a partially configured server. `.env` is for local development; deployment
systems should inject secrets and configuration instead of baking them into images.

## Runtime behavior and troubleshooting

The example uses port 5000 and `ENV=development`, which enables Uvicorn reload. Test/production modes disable reload. Open `http://localhost:5000/docs`, `/redoc`, or `/openapi.json` for the API schema. The versioned collection is `/api/v1/items/`.

`DEBUG`, `WORKERS`, and `METRICS_API_KEY` are not consumed settings. Setting a metrics key does not protect `/metrics`. [Settings validation](../app/config/environment.py) is the source of truth.

- Validation exits before serving requests: fix the named fields in `.env` or injected environment values.
- Database startup fails: check the async URL/driver, reachability, credentials, and schema permissions.
- Pytest cannot create temporary directories: use a writable disposable path with `python -m pytest -q --basetemp=.pytest-local-tmp`. Pytest may clear that directory; never choose a path containing needed data.
- Container configuration differs from local startup: `.env` is excluded from the image. Follow [Deployment](deployment.md).

Startup creates missing tables but does not migrate existing schemas; see [Architecture](architecture.md#persistence-and-migrations). Quality commands and fixture isolation are documented in [Testing](testing.md).
