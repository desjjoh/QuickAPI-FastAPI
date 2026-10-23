# Testing

[Documentation index](../README.md#documentation)

## Setup and test boundaries

Install [requirements.txt](../requirements.txt) in a Python 3.12 virtual environment. Markers and coverage settings live in [pyproject.toml](../pyproject.toml); job dependencies and commands live in [the Quality workflow](../.github/workflows/tests.yml).

| Layer | Location | Boundary |
| --- | --- | --- |
| Unit | `tests/unit/` | Isolated models, handlers, middleware, configuration, and utilities |
| Integration | `tests/integration/` | Real SQLite sessions/repositories, application stack, and error/OpenAPI integration |
| E2E | `tests/e2e/` | Complete app over HTTPX ASGI transport, lifespan, and isolated SQLite persistence |

[Shared fixtures](../tests/conftest.py) force test configuration and clear logging/request/metrics state. [Integration fixtures](../tests/integration/conftest.py) and [E2E fixtures](../tests/e2e/conftest.py) use disposable file-backed SQLite databases under pytest temporary paths. HTTP E2E runs in-process; it does not start Uvicorn, open network sockets, or verify MySQL.

## Quality gates and tests

Run the same static checks used by CI:

```bash
black --check app tests
ruff check app tests
mypy app
```

Every test has an explicit layer marker. CI first verifies that each layer collects
at least one test, preventing an accidentally empty suite from passing:

```bash
pytest --collect-only -q --no-cov -m unit
pytest --collect-only -q --no-cov -m integration
pytest --collect-only -q --no-cov -m e2e
pytest -q --no-cov -m unit
pytest -q --no-cov -m integration
pytest -q --no-cov -m e2e
```

The combined run enforces 90% overall coverage with branch measurement enabled; it does not enforce separate 90% statement and branch floors. CI additionally
requires 90% middleware coverage and 95% coverage for lifecycle, database, and API
packages:

```bash
pytest -q
shopt -s globstar
coverage report --fail-under=90 app/common/middleware/*.py
coverage report --fail-under=95 app/common/handlers/lifecycle_handler.py
coverage report --fail-under=95 app/database/**/*.py
coverage report --fail-under=95 app/api/**/*.py
```

The `shopt` and recursive glob commands require Bash, matching Ubuntu CI. PowerShell can run `python -m pytest -q` for the overall gate and `python -m coverage report --fail-under=95 app/common/handlers/lifecycle_handler.py` for the single-file gate; run shell-specific package commands in Bash or CI.

## CI sequence and verification limits

Pull requests and pushes to `main` run static analysis, then the unit/integration/E2E matrix, then combined coverage, then the production-container job. Layer runs disable coverage; combined coverage reruns all tests and applies overall and critical-package thresholds.

Container CI builds the image, starts it with explicit production settings and disposable SQLite, polls `/ready`, and reads `/api/v1/items/`. It does not test Compose, MySQL, container mutations, durable persistence, schema upgrades, restore, or rollback. See [Deployment](deployment.md).

Record the commit/environment and distinguish passed, failed, skipped/not run, and unavailable checks. A workflow definition is not evidence that a particular commit passed. This documentation update makes no new runtime or release-readiness claim.

## Regression coverage

Place tests at the boundary that owns the behavior: unit for isolated decisions, repository integration for transaction/query behavior, and HTTP for client-visible contracts. Protect consequential failure paths without mirroring implementation details. Track unresolved gaps in [Backlog](backlog.md).
