# Testing

[Documentation index](../README.md#documentation)

## Setup and test boundaries

Install [requirements-dev.txt](../requirements-dev.txt) in a fresh Python 3.12 virtual environment and run `python -m pip check`. Markers and coverage settings live in [pyproject.toml](../pyproject.toml); job dependencies and commands live in [the Quality workflow](../.github/workflows/tests.yml).

| Layer       | Location             | Boundary                                                                                  |
| ----------- | -------------------- | ----------------------------------------------------------------------------------------- |
| Unit        | `tests/unit/`        | Isolated models, handlers, middleware, configuration, and utilities                       |
| Integration | `tests/integration/` | Real SQLite/MySQL sessions/repositories, application stack, and error/OpenAPI integration |
| E2E         | `tests/e2e/`         | Complete app over HTTPX ASGI transport, lifespan, and isolated SQLite/MySQL persistence   |

[Shared fixtures](../tests/conftest.py) isolate configuration and logging/request/metrics state. Integration/E2E fixtures default to private SQLite files; the explicit [MySQL runner](mysql-testing.md) selects the guarded disposable MySQL target from `.env.test`. HTTP E2E uses in-process ASGI transport; socket behavior has separate Uvicorn tests.

## Quality gates and tests

Run the same static checks used by CI:

```bash
python -m black --check app tests scripts
python -m ruff check app tests scripts
python -m mypy app scripts
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

Pull requests, pushes to `main`/`staging`/`dev`, merge groups, and manual dispatch run static analysis, then the SQLite unit/integration/E2E matrix and separate disposable MySQL integration/E2E jobs, then combined coverage, then the production-container job. Layer runs disable coverage; combined coverage reruns all tests and applies overall and critical-package thresholds.

Container CI builds the image, starts it with explicit production settings and disposable SQLite, polls `/ready`, and reads `/api/v1/items/`. The image smoke remains SQLite-based; separate MySQL jobs test migrated repository/API persistence. The image smoke does not qualify MySQL container mutations, durable deployment storage, representative data upgrades, restore, or rollback. See [Deployment](deployment.md).

Record the commit/environment and distinguish passed, failed, skipped/not run, and unavailable checks. A workflow definition is not evidence that a particular commit passed.

Hosted check names and required-check configuration are documented in [Branch protections](branch-protection.md). Dated execution results belong to [Verification](verification.md); each result applies to its recorded source/environment.

## Regression coverage

Place tests at the boundary that owns the behavior: unit for isolated decisions, repository integration for transaction/query behavior, and HTTP for client-visible contracts. Protect consequential failure paths without mirroring implementation details. Track unresolved gaps in [Backlog](backlog.md).

## Verification boundaries

Use Python 3.12 for local checks. An unsupported interpreter or an unavailable service
is an execution limitation, not a passing or failing application test. Record the
source identity, environment, and outcome in [Verification](verification.md).

Automated persistence tests run against SQLite and disposable MySQL; the image smoke
still uses SQLite. The workflow does not qualify representative future data upgrades/rollback, backup restoration, or candidate-bound
release publication. It has no aggregate fail-closed job. Required checks must be
configured separately in GitHub; see [Branch protections](branch-protection.md).
Additional verification requirements are tracked in [Backlog](backlog.md).

## HTTP deadline and streaming checks

The [timeout test guide](request-timeouts.md#verification) describes focused unit checks and real loopback Uvicorn integration checks on both h11 and httptools. The socket checks run in the existing integration layer; they are not production-only endpoints or MySQL verification.

## Request outcome regression coverage

[Outcome unit tests](../tests/unit/middleware/test_request_outcome.py) exercise
completion/abort races, header state, channel failures, cancellation, post-response
cleanup, duplicate/late subscribers, method bounds, and full declared mount templates.
[Application and real-server checks](../tests/integration/middleware/test_request_outcomes.py)
verify bounded series across varying IDs, unknown paths and methods, completed policy
rejections/final 500s, concurrent request correlation, and matching log/metric durations.
Eight outcome cases run real Uvicorn sockets with both h11 and httptools: pre-header
408, ordinary-handler disconnect, streaming timeout, and streaming disconnect. They
assert metrics/access logs settle before cancellation-resistant cleanup and remain
unchanged after it. These supplement twelve socket deadline cases in
[timeout tests](../tests/integration/middleware/test_timeout_server.py); HTTPX ASGI
transport alone cannot prove socket disconnect or truncated-body behavior.

## HTTP policy regression coverage

[Environment tests](../tests/unit/config/test_environment.py) cover defaults, exact
CSV syntax, bounds/relationships, malformed values, process/dotenv precedence, and
agreement between commented example values and code defaults.
[Proxy unit tests](../tests/unit/middleware/test_trusted_proxy.py) cover IPv4/IPv6,
right-to-left trust chains, malformed/duplicate/unsupported forwarding, direct peers,
non-HTTP scopes, and original header budgets.
[Policy integration tests](../tests/integration/middleware/test_http_policy.py)
exercise configured browser preflight/response headers, custom header/media policy,
raw-header and body/method rejection, and six real Uvicorn socket cases across h11
and httptools for trusted/untrusted identity and configured response deadlines.
The socket harness disables Uvicorn proxy rewriting to exercise app-owned trust.
Deployment-specific slow-header protection remains unverified and open.

## Operational exposure regression coverage

[Operational integration tests](../tests/integration/middleware/test_operational_exposure.py)
exercise environment defaults, all eight independent flag combinations, disabled route
families/methods/assets/redirects, mounted paths, forwarding behavior, handler non-execution,
per-app route isolation, registered OpenAPI paths, continued metric collection, and
minimal public probes with dependencies up/down. Two real-server cases cover production
defaults across h11/httptools. Environment tests also reject ambiguous flag values and
verify explicit overrides. Controller/model/E2E/OpenAPI checks enforce the minimal
public readiness contract.

## Bounded rate-limit regression coverage

[Core limiter tests](../tests/unit/config/test_rate_limiter.py) cover exact rolling
boundaries/ring reuse, sustained rejection without growth/extended expiry, distinct
identity floods, tracked-client admission at capacity, ordered reclamation, long keys,
instance independence, constructor bounds, and atomic thread admission.
[HTTP tests](../tests/integration/middleware/test_rate_limiting.py) cover remaining
retry timing, 429/503 envelopes, trusted/untrusted identity, probe/other-route accounting,
preflights and CORS rejection ordering, raw-header protection, and favicon GET/HEAD
exemption. Two real Uvicorn cases exercise concurrent bursts, isolation, capacity,
and exact recovery across h11/httptools. Environment tests cover all three settings,
strict types/ranges, the combined slot ceiling, and env-example/default consistency.

## Logging privacy checks

[Logging tests](logging.md#verification) capture actual console/JSON output, including
fresh processes and real server failures. They verify level filtering, single-line
presentation, metadata exclusion, request correlation after context cleanup, diagnostic
allowlists/fingerprints, safe bootstrap failures, and Windows-compatible output. The
complete suite also protects request/timeout outcome semantics and public error contracts.

## Migration checks

`python -m pytest -q tests/integration/database/test_migrations.py --no-cov` exercises the baseline, read-only startup rejection, model comparison, repeat application, incompatible history, downgrade/reapply, and online/offline execution. Persistence fixtures apply the migration chain explicitly rather than creating ORM tables. See [Migrations](migrations.md) for commands and limitations.

## Disposable MySQL commands

`python -m scripts.test_db test` starts and migrates isolated MySQL, runs integration/E2E tests, and cleans up. Use `--layer integration` or `--layer e2e` for the separate CI selections. [Disposable MySQL testing](mysql-testing.md) documents `.env.test`, migration generation/application, safety checks, and inspection/reset commands.

## Database capacity and TLS

[Database transport tests](database-settings.md#verification-commands) exercise actual pool saturation, queue expiry/cancellation, invalidation/disposal, and stalled connection setup. Dedicated TLS cases run through `python -m scripts.test_db tls` and are part of the MySQL integration CI job. They are explicitly deselected from default compatibility runs, with their results recorded separately.
