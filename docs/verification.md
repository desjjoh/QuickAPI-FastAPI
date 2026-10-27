# Verification record

[Documentation index](../README.md#documentation)

## Phase 1A — Environment and dependencies

Verified on 2026-10-27 against the working tree based on commit `cfa6bdf27f5cdb4a7190ab17d948f4636ee8bbd5`, including the uncommitted dependency/workflow changes below. Application source and tests were unchanged. This is local Windows and Docker evidence, not a hosted GitHub CI result or a committed release candidate.

### Implemented

- Retained pip and manually maintained exact pins: 31 runtime packages and 18 development-only packages, including transitive requirements. Existing explicit versions were retained; coverage is now pinned to the previously installed 7.15.4.
- Development requirements include runtime requirements once. Removed conflicting older pytest/pytest-asyncio pins.
- CI installs development requirements and runs `pip check`; Docker installs runtime requirements and runs `pip check`. Quality commands use the selected interpreter through `python -m`.
- Installed official Windows Python 3.12.10 alongside 3.14 without changing PATH/default Python. Recreated `.venv` with 3.12; preserved the old environment as ignored `.venv-python314`. A separate ignored `.venv-runtime` verifies runtime-only installation. Both auxiliary environments are excluded from Docker context.
- Updated editor interpreter selection and setup/maintenance instructions. Linux verification used Python 3.12.16 from the resolved container image; Windows 3.12.10 is the official installer available through winget, not a claim of latest patch parity.

### Passed

| Check | Result |
| --- | --- |
| Fresh Windows development/runtime installs | Successful; `pip check` passed independently in both |
| Development manifest consistency | All 49 application/tool pins unique, installed versions match, no unpinned installed application packages |
| Windows formatting/lint/types | Black: 109 files unchanged; Ruff passed; mypy: 46 source files |
| Windows complete suite | 357 passed; 93.99% overall coverage with branch measurement |
| Layer selection | Unit 189; integration 56; E2E 112; every selector non-empty |
| Fresh Linux development install | Successful inside a disposable runtime-image container; `pip check` passed |
| Linux formatting/lint/types | Black: 109 files unchanged; Ruff passed; mypy: 46 source files |
| Linux complete suite | 357 passed; 94.15% overall coverage with branch measurement |
| Linux critical coverage gates | Middleware 92% against 90%; lifecycle 97%, database 100%, API 99% against 95% |
| Runtime-only contents | Windows and Linux imports/distribution checks exclude Black, Ruff, mypy, pytest, HTTPX, and coverage; Linux check also excludes pytest plugins |
| Built-image dependency consistency | `pip check` passed on final runtime image |
| Built-image smoke | Disposable SQLite `/ready` successful and `/api/v1/items/` returned an empty collection over a loopback-only ephemeral port; container stopped/removed |

Windows complete-suite command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-local-tmp
```

Linux verification installed `requirements-dev.txt` into a disposable container from the runtime image, mounted source read-only, ran the same static checks and full suite, and applied all four package coverage gates from the workflow. Cache, database, and coverage output went to container `/tmp`; no test-only dependencies were added to the saved runtime image.

Final local Docker image ID: `sha256:823da9b4d5b9981a120afe5b1505d6f1c519f8f1d55dc296685cffdbcafd8542` (`quickapi-fastapi:phase-1a`). This is a local image identity, not published release evidence.

| Verified input | SHA-256 |
| --- | --- |
| `requirements.txt` | `bbba8ec97d5ece47e096a520f35013ab9de4db6ea1354ded43c466c51efb5be9` |
| `requirements-dev.txt` | `78e2697eed46117b133a6748bd74d200f60c03c2f7b75d10b08dd12937011140` |
| `Dockerfile` | `fc03a29738267aaedb9e314df58aa0503fdcee62d3c38e8c22c4a35c921a9c3b` |
| `.github/workflows/tests.yml` | `a0648f2aa0c16212276d5704a7181c68e962e39fa817460d1d11e21c6b7e6bf9` |

### Limits and remaining work

- Follow-up activation repair: the initial sandboxed `venv` creation stopped at pip bootstrap before generating activation scripts. Installing pip/dependencies separately did not finish that step. Re-ran `venv --without-pip` against the existing development/runtime environments to generate the standard scripts without clearing installed packages. Verified PowerShell activation selects `.venv/Scripts/python.exe` on Python 3.12.10, imports FastAPI/SQLAlchemy/pytest, and passes `pip check`. Editor defaults now name that executable explicitly; an existing VS Code interpreter selection may still need to be changed through **Python: Select Interpreter**.

- Initial sandbox attempts could not reach package indexes, bootstrap pip temporary files, or access Docker's named pipe. Approved execution outside those restrictions completed the checks above. These are environment restrictions, not application test failures.
- Hosted CI and actual branch protection/status-check enforcement were not executed or changed. They remain in phases 1B/6E.
- Container smoke and persistence tests still use SQLite. MySQL qualification, migrations, security scans, non-root/digest hardening, and release attestations remain in their scheduled phases.
- Existing third-party debug output was visible during the runtime smoke even with `LOG_LEVEL=ERROR`; retain this observation for logging phase 2D.
- The historic Python 3.14-only mismatch is resolved for this local baseline; it was unavailable verification at the time, not a failed test run. The globally selected `python` can still be 3.14 outside the activated environment.

## Phase 1C — Request timeout correctness

Verified on 2026-10-27 against the working tree based on commit `45d224253a4907f140944eac36ce9f7d894c9379`, including the uncommitted timeout/test changes fingerprinted below. This is the timeout/streaming phase called 1B in the earlier outline; expanded phase 1B (startup/branch protections) remains pending. QuickAPI-Express's request timeout, request lifecycle, and real-socket tests were inspected as the behavioral reference.

### Implemented behavior

Response-start/completion tracking prevents duplicate or late output. Before headers, owned expiry returns the existing JSON 408 envelope; after headers it raises a dedicated abort error so Uvicorn closes the incomplete response. Completed responses no longer expire while cleanup continues. A single bounded receive owner preserves body messages and observes available disconnects. External cancellation and unrelated downstream/receive timeouts are preserved. Cancelled downstream work remains referenced until it settles, and late failures are observed without logging exception text.

Renamed `header_timeout` to `first_body_timeout`; all receive/total budgets now reject non-finite/non-positive configuration. No new production routes, environment variables, package versions, or workflow jobs were introduced. [Request deadlines](request-timeouts.md) documents body prefetch/disconnect limits, async cancellation-safe resource cleanup, the lack of a true TCP header deadline, and the separate SQL/shutdown guarantees still to implement.

### Passed

| Check | Result |
| --- | --- |
| Windows Python 3.12.10 complete suite | 393 passed; 94.75% overall coverage with branch measurement |
| Linux Python 3.12.16 complete suite | 393 passed; 94.90% overall coverage with branch measurement |
| Formatting, lint, typing on both platforms | Black: 110 files unchanged; Ruff passed; mypy: 46 source files |
| Linux critical coverage gates | Middleware 94% against 90%; lifecycle 97%, database 100%, API 99% against 95% |
| Timeout middleware coverage | 99% with branch measurement on both platforms |
| Real-socket regression checks on both platforms | Twelve cases across h11/httptools: pre-header 408 before delayed cleanup, truncated stream before delayed cleanup, ordinary-handler disconnect, stalled-body JSON 408, reused keep-alive connection after deadlines, stream-generator disconnect cleanup |
| Updated runtime image | Build/dependency check passed; `/ready` and item collection smoke passed against disposable SQLite; loopback test container stopped/removed |

The Linux suite ran inside a disposable container with a read-only working-tree mount and temporary coverage/cache/database outputs. The actual application middleware stack was used by the socket fixtures, with test-only endpoints and HTTP-only Uvicorn configuration. Async generator resource cleanup in the Starlette/AnyIO fixture explicitly shields its cleanup await; this is not evidence that arbitrary unshielded user cleanup always completes.

During development the new regression checks exposed a receive-side `TimeoutError` being mistaken for disconnect because it subclasses `OSError`; that classification was corrected before the passing full runs above. HTTP socket fixtures disable WebSockets so unrelated legacy WebSocket-import deprecations do not prevent testing HTTP. Production WebSocket behavior was not changed or qualified.

Updated local runtime image ID: `sha256:393e223f296ac3057a13eaff81a642c7ff168fd55de670c28ab027eade0afed3` (`quickapi-fastapi:phase-timeout`). Hosted CI/publication, MySQL qualification, and deployment ingress behavior were not run. This does not establish database rollback, cancellation of running SQL/thread work, or full application shutdown draining.

| Verified input | SHA-256 |
| --- | --- |
| `app/common/middleware/request_timeout.py` | `65bebd95db026c1755cf67e59f62b3527b62da12e586038296324d521d1abc81` |
| `tests/unit/middleware/test_request_timeout.py` | `31b7dacb44efc6cf090546f3acbfa53088077b4ba378f6f0f6ff02c05fa86da4` |
| `tests/integration/middleware/test_timeout_server.py` | `de9d176e8077d8140bccb6ddb0ad7adf59c3b5b3e731dff43d2b4910e4b1d444` |
| `tests/integration/errors/test_middleware_rejections.py` | `3defe9e357970ffe60fa842decee4d6c03fa7ccac427c68ee95d4133bf162106` |


### Editor diagnostic follow-up

Resolved the four reported Pylance diagnostics after the full-suite snapshot above: task retention/removal now stays inside the middleware through `track_work`, the async context-manager fixture declares `AsyncGenerator[int, None]`, and body-deadline parameter cases have an explicit `list[tuple[list[Message], str]]` type.

Verification of this follow-up: Pyright strict mode on all three affected files reported **0 errors, 0 warnings, 0 informations**; Black, Ruff, and application mypy passed; **39 focused timeout/socket tests passed** on Windows Python 3.12. No diagnostic suppressions or project dependencies were added. The full Windows/Linux results and image identity above refer to the preceding implementation snapshot; those broader checks were not repeated for this typing/class-boundary follow-up.
