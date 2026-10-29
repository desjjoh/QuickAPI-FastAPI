# Testing

[Documentation index](../README.md#documentation)

[Mutation transactions](transactions.md) defines the route decorator, shared session,
repository caller obligations, and response-before-commit verification.

[Graceful shutdown](shutdown.md) defines request admission, draining, deadlines,
entrypoint ownership, and process verification.

[Database readiness and recovery](database-lifecycle.md) documents probe deadlines,
shared checks, startup cleanup, and runtime recovery behavior.

## Setup and test boundaries

Use Python 3.12 and install [requirements-dev.txt](../requirements-dev.txt) in the
project virtual environment. Verify `python --version` and `python -m pip check`.
On Windows, activate `.venv\Scripts\Activate.ps1` or invoke
`.venv\Scripts\python.exe` directly. Global Python is not the project's interpreter.

MySQL through `mysql+asyncmy` is the only supported database. All persistence,
migration, pool/session, readiness/recovery, and database-backed process checks use
real disposable MySQL. Unit checks use test doubles and need no running database.

| Layer | Location | Boundary |
| --- | --- | --- |
| Unit | `tests/unit/` | Isolated models, handlers, middleware, configuration and utilities |
| Integration | `tests/integration/` | MySQL repositories/migrations, application stack, real sockets and processes |
| E2E | `tests/e2e/` | Complete application lifespan and HTTP over isolated MySQL persistence |

Fixtures load `.env.test`, verify live identity, and hold an exclusive reset guard.
Destructive migration cases restore the baseline before releasing that guard.
Development `.env` and the persistent development database are separate.

## Commands

From the repository root with Docker running:

```powershell
# Start authenticated MySQL, migrate, run the full suite with coverage, and clean up.
python -m scripts.test_db test
# Individual persistence layers, without coverage.
python -m scripts.test_db test --layer integration
python -m scripts.test_db test --layer e2e
# Separate generated-certificate MySQL server; cleaned up afterward.
python -m scripts.test_db tls
```

Without Docker, run unit tests only:

```powershell
python -m pytest -q -m unit --no-cov
```

For focused direct pytest checks, use `python -m scripts.test_db up` and
`python -m scripts.test_db migrate` first. Direct `python -m pytest` loads the same
guarded MySQL configuration and fails if the server is unavailable; it does not
start Docker or substitute a different backend. Use `--no-cov` for partial selections
that cannot meet the full application's coverage threshold.

Pytest `.` means passed, `s` means skipped, and `F` means failed. Use `-rs` to show
skip reasons. Windows skips the two POSIX-only native entrypoint signal cases;
Linux executes them. The MySQL outage case runs on both platforms. Five dedicated
TLS cases are explicitly deselected from ordinary runs and run via the TLS command.
Test counts are recorded in [Verification](verification.md), not fixed as a contract.

## Quality gates

```powershell
python -m black --check app tests scripts
python -m ruff check app tests scripts
python -m mypy app scripts
```

The full MySQL run measures branch coverage and requires 90% overall. CI additionally
requires 90% middleware and 95% lifecycle, database-package, and API coverage. Bash
commands matching CI are:

```bash
python -m scripts.test_db test
shopt -s globstar
coverage report --fail-under=90 app/common/middleware/*.py
coverage report --fail-under=95 app/common/handlers/lifecycle_handler.py
coverage report --fail-under=95 app/database/**/*.py
coverage report --fail-under=95 app/api/**/*.py
```

The shell glob commands require Bash. PowerShell can use
`python -m coverage report --fail-under=95 --include='app/database/*'` for a package.
An unavailable service is a failure to execute the persistence suite, never a pass.

## CI and image qualification

The Quality workflow runs static analysis, unit checks, MySQL integration/E2E jobs,
a full MySQL coverage run, and built-image MySQL qualification. Database jobs own
independent disposable infrastructure. Layer collection must be nonempty; failures
collect bounded logs and cleanup is attempted. Dedicated TLS checks remain in the
MySQL integration job.

```powershell
docker build -t quickapi-fastapi:ci .
python -m scripts.test_image
```

The image command verifies explicit migrations, CRUD, probes, static assets,
production exposure defaults, dependencies, and graceful Docker termination against
an independent MySQL server. See [Deployment](deployment.md) for ownership and limits.

Required check names and removal of obsolete duplicate contexts are documented in
[Branch protections](branch-protection.md). Workflow definitions and local checks do
not establish hosted success or ruleset enforcement. There is no aggregate
fail-closed final job yet. Representative future migrations, restart/persistence,
backup restoration and candidate-bound release publication remain separately scoped.

## Regression coverage

Place tests at the boundary that owns the behavior. Record actual source identity,
environment, passed/failed/skipped results and limitations in
[Verification](verification.md). Historical records describe their original source
and do not define the current supported database configuration.

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
