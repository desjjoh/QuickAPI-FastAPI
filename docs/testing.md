# Testing

[Documentation index](../README.md#documentation)

## Setup and test boundaries

Install [requirements-dev.txt](../requirements-dev.txt) in a fresh Python 3.12 virtual environment and run `python -m pip check`. Markers and coverage settings live in [pyproject.toml](../pyproject.toml); job dependencies and commands live in [the Quality workflow](../.github/workflows/tests.yml).

| Layer | Location | Boundary |
| --- | --- | --- |
| Unit | `tests/unit/` | Isolated models, handlers, middleware, configuration, and utilities |
| Integration | `tests/integration/` | Real SQLite sessions/repositories, application stack, and error/OpenAPI integration |
| E2E | `tests/e2e/` | Complete app over HTTPX ASGI transport, lifespan, and isolated SQLite persistence |

[Shared fixtures](../tests/conftest.py) force test configuration and clear logging/request/metrics state. [Integration fixtures](../tests/integration/conftest.py) and [E2E fixtures](../tests/e2e/conftest.py) use disposable file-backed SQLite databases under pytest temporary paths. HTTP E2E runs in-process; it does not start Uvicorn, open network sockets, or verify MySQL.

## Quality gates and tests

Run the same static checks used by CI:

```bash
python -m black --check app tests
python -m ruff check app tests
python -m mypy app
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

## Roadmap verification baseline

The reported local execution attempt was unavailable because the machine had Python 3.14 while this project targets Python 3.12. That is an environment mismatch, not a failed test run, and does not establish current runtime availability. [Roadmap phase 1A](roadmap.md#1a-environment-and-dependencies) now provides a supported execution path; see [Verification](verification.md) for fresh Windows/Linux results and remaining limitations.

The [roadmap](roadmap.md) schedules disposable MySQL integration/E2E and migration-upgrade/rollback evidence in 3B/3C, MySQL runtime-image smoke in 6B, aggregate fail-closed CI and required-check verification in 6D/6E, and candidate-bound release evidence in milestone 7. These are planned checks, not capabilities or passing results supplied by the current workflow.
