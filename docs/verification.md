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


## Phase 1B — Startup and branch protections

Verified on 2026-10-27 against the working tree based on commit `8b0246a524a979aa902575d9519e025c847819e1`, including the uncommitted configuration changes below. Application source, dependency pins, and tests were not changed by this phase. Existing documentation edits were retained.

### Passed locally

- `docker compose config --quiet` succeeds. Structural checks confirm the fixed internal API port/mode, authenticated MySQL health dependency, loopback-only published ports, named-volume storage, and absence of fixed container names.
- A uniquely named project `quickapi-fastapi-1b-a8601e5c` built the runtime image and started MySQL 8.4.6 plus API through `up --build --detach --wait`. A temporary override selected `.env.example` for API configuration instead of developer secrets; host ports were allocated dynamically. No application/database topology was substituted.
- Both services became healthy. A POST returned 201, its subsequent GET returned the expected name and price 12.34, and readiness succeeded.
- All project containers/network were removed with `down` while retaining the named volume. A second `up --detach --wait` recreated both containers/network and the earlier item was still readable with the expected fields.
- Only this disposable project's containers/network/volume were removed at the end. Existing `.env` and development data were not edited or deleted. No permanent local stack was left running.
- Windows Python 3.12.10 static checks passed: Black 110 files unchanged, Ruff clean, mypy 46 source files. Complete suite: **393 passed**, **94.76%** overall coverage with branch measurement.
- Workflow YAML semantic checks confirm unchanged job/check identities and job dependencies, all PRs, pushes to main/staging/dev, merge-group/manual events, read-only contents permissions, and cancellation of superseded runs.

Local API image ID: `sha256:29546e9e6a31939cf88eb9c4668ad1363eba1217bfbfd959083a40fbb63739cc` (`quickapi-fastapi:local`). Compose version: 5.5.1. This is local startup/persistence evidence, not an immutable published release or a MySQL-backed CI/release qualification gate.

### Verified on GitHub

- FastAPI ruleset 25976668 is active on main/dev/staging and matches Express ruleset 25689316 on structural PR/merge/bypass/deletion/non-fast-forward settings. Its required-status-check list is empty; Express requires `Deployment gate`.
- NestJS rulesets 16198248/16198302/16198404 use their own `Check`/`Migration Check` contexts; main/staging require up-to-date checks while dev does not. Those names are not copied to FastAPI.
- Successful hosted Quality run [39889071406](https://github.com/desjjoh/QuickAPI-FastAPI/actions/runs/39889071406), dated 2026-10-23 at SHA `cfa6bdf27f5cdb4a7190ab17d948f4636ee8bbd5`, emitted `static-analysis`, `test-layers (unit)`, `test-layers (integration)`, `test-layers (e2e)`, `combined-coverage`, and `production-container`, all successful. This is historical exact-SHA evidence, not a pass for today's configuration.
- main/dev and the milestone branch existed in the observed remote branch list; staging was not listed, but its protection target is already configured. No branches were created/reset.

### Pending / unavailable

The connector permits ruleset reads but has no administrative write tool; earlier native Firefox access was blocked by browser URL-policy support. No remote protection setting was changed. [The six-check configuration](branch-protection.md#remaining-manual-setting) must still be saved and verified before marking all of 1B complete. The proposed workflow triggers need a hosted run after the normal push/PR process; this task did not publish commits or open/merge a PR.

The existing CI suites/container smoke remain SQLite-backed. The local MySQL startup check is not migration, target-engine failure-path, backup/restore, TLS, or release-pipeline evidence. Those tasks remain in milestones 3, 6, 7, and 8. Linux complete-suite repetition was not needed for this configuration-only phase; the Compose runtime itself ran on Linux/MySQL.

| Verified phase 1B input | SHA-256 |
| --- | --- |
| `docker-compose.yaml` | `4f60c503e1ba4b77f279dc9725c33cee7be94b29f244512147caf8145c7d2809` |
| `.env.example` | `38f6a8837a1170874034c8bf1b423d183a58706f600f4bd6a5dbda7042bec903` |
| `.github/workflows/tests.yml` | `c7b193844a343478993b5b3589ec12fb5189d9cab4ead27a5b1f4302a2c7d690` |


### Optional published-port validation follow-up

`API_PUBLISHED_PORT` and `MYSQL_PUBLISHED_PORT` are now declared settings. Missing/empty values default to 8000/3308, and supplied values require whole-number ports from 1 through 65535. Compose forwards the resolved publishing values into the API environment; these fields do not change the internal listener's `PORT`. Comments are synchronized in `.env.example` and the gitignored local `.env`, with optional overrides remaining commented out.

Passed: Windows full suite **411 tests**, **94.77%** overall coverage with branch measurement; Black/Ruff/mypy; strict Pyright on affected validator/test/fixture files (**0 diagnostics**); Compose default/custom mapping-to-environment consistency; Linux runtime checks of custom overrides, blank defaults, and malformed/range/type rejection. Local runtime image: `sha256:655330da7d77d04e0dae467c2003091c9286233a64617b3d5835d7145ed565a9`. No services or database data were started/changed for that Linux validation check. The Linux complete suite and hosted CI were not repeated for this follow-up; branch-check administration remains pending.

| Verified follow-up input | SHA-256 |
| --- | --- |
| `app/config/environment.py` | `dd7f90723c8fa2109b295ab2e66e8e4cab4ac62e5493c1d44dbc30f4bba7e994` |
| `tests/unit/config/test_environment.py` | `02ef5333e269972e306debb879f01adbc331f3c9e25c1cd742b07a44c56ac0e8` |
| `tests/conftest.py` | `52ddfdf09c61e487cd08b7c87dec7dbee834af8be25618f69f7184038987252e` |
| `docker-compose.yaml` | `9374cd60eabc3f028a40f2456ca429f45d819ffeffe59fa1c0d221f3c0b9da93` |
| `.env.example` | `bfa1a4e6ce6097f4e3dd4e1a188c14643d74fc16c31470c569960b8b0628b3c2` |


## Phase 1D - Metrics and request outcomes

Verified on 2026-10-27 against the working tree based on commit
`9bc06651d4f9da5fb64df5b4b71f57b04164492b`, including the uncommitted inputs
fingerprinted below. Express's request-outcome handler and both sibling metric
configurations were inspected directly as references.

### Implemented behavior

One outer ASGI observation covers final server-error responses and feeds logging
and metrics before policy middleware can reject a request. Completion, disconnect,
channel failure, cancellation, and owned stream expiry settle once. Durations end at
response completion/abort, independently of cleanup or late work. Completed 408/500
responses are distinct from incomplete streams; aborts receive no fabricated status.
Declared route/mount templates and bounded methods replace raw URL labels. The five
operational-path exclusions remain. Python logging levels/console layout and error
messages/envelopes are preserved. No dependencies, environment variables, or CI jobs
were added. See [the contract and dashboard migration](deployment.md#metrics-and-request-outcomes).

### Passed

| Check | Result |
| --- | --- |
| Windows Python 3.12.10 complete suite | 446 passed; 95.32% overall branch-measured coverage |
| Linux Python 3.12.16 complete suite | 446 passed; 95.47% overall branch-measured coverage |
| Linux critical coverage gates | Middleware 95% against 90%; lifecycle 97%, database 100%, API 99% against 95% |
| Formatting, lint, application types | Black: 113 files unchanged; Ruff passed; mypy: 47 source files, on Windows and Linux |
| Strict Pyright | All 15 changed Python files checked; zero diagnostics |
| Documentation | 103 relative links/anchors verified |
| Outcome observer coverage | 100% statements and branches |
| Real-server coverage | Eight new outcome cases plus twelve existing deadline cases, across h11 and httptools |
| Runtime image smoke | Readiness, SQLite item listing, completed counter/duration exposition, legacy-series absence, operational exclusions, and pip check passed; disposable loopback container removed |

The new tests also exercise cardinality across varying IDs/unknown URLs/methods,
405 route matching, declared dynamic and repeated mounts, actual final 500s, early
policy failures, correlation after context cleanup and between concurrent requests,
identical access-log/metric durations, duplicate/late subscribers, terminal-event
races, and timing/count stability after delayed cleanup. Database tests and image
smoke still use SQLite; this is not MySQL/release-pipeline qualification.

Local runtime image: `sha256:580017393e8c8ea335f78f32d0270a73d2a06cf44e4978952378df286d9e85f4`
(`quickapi-fastapi:phase-1d`). Linux checks install development requirements into a
disposable container; the saved runtime image retains runtime requirements only.
Source is mounted read-only and coverage/cache/database output goes to `/tmp`.

### Not run / remaining

Hosted CI for this working tree was not run. Phase 1B's manual required-check
configuration remains pending; completing 1D does not assert branch enforcement.
Broader logging/privacy work remains phase 2D. Socket observations establish the
server-side outcome, not acknowledgement of byte consumption by the peer; existing
receive/backpressure and cooperative-cancellation limits still apply.

| Verified phase 1D input | SHA-256 |
| --- | --- |
| `app/common/middleware/request_outcome.py` | `17adf8a617d37fff3e12ef239678307cc5639a0ea38aad4eb66a95f7020c3a9e` |
| `app/common/middleware/request_logger.py` | `7f0a3f76f745c9e8c6687f7cc4a9258313d98853b82ea38e94aed63ce969842e` |
| `app/common/middleware/prometheus_metrics.py` | `6e9faacb39e0d67f96f1a2f7766cdeb5286e7943af728d9d751809bcb9ee1ad0` |
| `app/common/middleware/request_timeout.py` | `beb76b8a496516805dd12cf4dd83c235cf40d644df94599e8344b11932922437` |
| `app/config/application.py` | `d14387dede0616addad3ad96d3ac4bda80a794813416be5f992f2574e3705e1f` |
| `app/config/metrics.py` | `972c7263d4ba2ec31450c5eb9b979b9ec2ccf38c6c842e0054f52dc1010ba060` |
| `tests/unit/middleware/test_request_outcome.py` | `523601512772dc99f50314f7f7eeb8b9b62f122d19214b14bed969cd161b6e75` |
| `tests/integration/middleware/test_request_outcomes.py` | `f9fedd4eae8994c91f57bf85c5c1e47395c385cd89154f7ab54c38a53249ee44` |


## Phase 2A - Validated HTTP configuration

Verified on 2026-10-27 against the working tree based on commit
`609e143f1766e4da60f83fc4b011c4e19e3d3664`, including the uncommitted inputs
fingerprinted below. Express/NestJS env examples and Express validation were inspected
as naming/comment/default references. Application configuration is complete locally;
true server/ingress header and whole-upload receive protection remains open.

### Implemented behavior

Pydantic Settings owns defaults and validates optional CSV/boolean/numeric env
overrides for CORS, proxy trust, response/body deadlines, parsed-header/body budgets,
and allowed methods/media types. Normal precedence is process environment over `.env`
over defaults. Required identity/database/listener values retain their existing role.
The env example is grouped and commented with actual defaults, units, bounds, and
relationships; the local gitignored `.env` received the same shared comments while
all pre-existing effective values were preserved. No local values are recorded here.

CORS now uses exact browser-serialized origins with localhost:3000 as its default,
replacing wildcard access. Requests without Origin receive no CORS response headers.
Explicit IP/CIDR proxy trust defaults to empty; only a trusted connecting peer can
supply the two supported forwarding headers. Validated right-to-left chains resolve
identity before context/limiting. The normal entrypoint disables Uvicorn's own proxy
rewriting; external launchers must do likewise. Parsed-header limits now precede
preflight short-circuiting and sanitizer filtering; consumed proxy headers cannot
evade their original budgets. Existing error envelope and deadline behavior remain.

See [HTTP configuration](http-policy.md) for settings/defaults and rollout details.
Rate-limit algorithm/configuration and operational exposure remain phases 2C/2B.
No dependency pins, database schema, or workflow definitions changed.

### Passed

| Check | Result |
| --- | --- |
| Windows Python 3.12.10 complete suite | 606 passed; 95.77% overall branch-measured coverage |
| Linux Python 3.12.16 complete suite | 606 passed; 95.89% overall branch-measured coverage |
| Formatting, lint, application types on both platforms | Black: 117 files unchanged; Ruff passed; mypy: 49 source files |
| Strict Pyright | All 14 affected Python source/test files; zero diagnostics |
| Linux critical coverage gates | Middleware 96% against 90%; lifecycle 97%, database 100%, API 99% against 95% |
| Proxy middleware and shared policy helpers | 100% statements/branches |
| Env contract | Default/override and file/process/constructor precedence, malformed syntax/types/ranges/relationships, list bounds, and example/default consistency |
| Real-server checks | Six new cases across h11/httptools for trusted/untrusted identity and configured deadlines; existing twenty socket cases retained |
| Runtime image smoke | Readiness, custom origin/credentials/body budget, denied origin, untrusted forwarding rejection, and pip check; disposable container removed |
| Local env preservation | Existing effective values preserved; shared comments synchronized with `.env.example` |
| Documentation | 118 relative links/anchors verified |

Linux checks installed development requirements into a disposable runtime-image
container with source mounted read-only and test/coverage/cache output in `/tmp`.
The final saved runtime image contains runtime dependencies only. Local image:
`sha256:f0f9f948a0bb2312a8123fb9286528e07074846494ff2a50b0010f98d0738949`
(`quickapi-fastapi:phase-2a`). These are local checks, not hosted/release evidence.

### Not run / remaining

Hosted CI for this working tree was not run. MySQL was not requalified; persistence
and image smoke remain SQLite-backed. Real ingress trust/direct-port restrictions,
slow-header/whole-upload receive protection, and their deployed socket verification
remain open. No ineffective header-timeout variable is exposed: body/response/keepalive
deadlines do not establish a TCP header-receive guarantee. External server commands
that rewrite the peer before ASGI violate the documented proxy ownership contract.
Broader logging/privacy and endpoint-exposure work remain in their scheduled phases.

| Verified phase 2A input | SHA-256 |
| --- | --- |
| `.env.example` | `32d19da6fa1e8c87a9a3ae7bf62f2f428690344e7eaa326333bf910718653b7b` |
| `app/config/environment.py` | `341d1b47c74b0b95df2f5c64c3af0d521fd580ba98a73b5183a9e839205e7579` |
| `app/config/http_policy.py` | `3947ff9fa9c0073f98bff2bcff2eb8f86dafb3f75163a9697fe366779dbfc649` |
| `app/config/application.py` | `ce7965f4e84b9556d36f8891fa482d514e01ababa88f0d9667c9e980e1f1a40c` |
| `app/main.py` | `5e0d98c466bc82928a3ff8f31e5f81ccc479bd13a07ef7c2ee4da3a7e30f65fb` |
| `app/common/middleware/trusted_proxy.py` | `644d1e4bf8c6f1c391a5e8a4a7833a0e9840fb00d23c413590c494f782747bdd` |
| `app/common/middleware/cors.py` | `33cf0890ddf1813b66da46678dd9b58fb83f5cb09f678a729d6db50e9125a303` |
| `app/common/middleware/request_header_sanitization.py` | `a0bdb19dc643df02bb3ee523f93810dacdfd5450c4c57abcf3dbb5c5d79a8e67` |
| `tests/unit/config/test_environment.py` | `b59d16c26ebd3493169c45b037290ccc7e0aab7adfaa5e82584297e410e84b00` |
| `tests/unit/middleware/test_trusted_proxy.py` | `4db073b4bc3229ba887df662e105e051cf77bed4b12d2b9272e548e4f8faff15` |
| `tests/integration/middleware/test_http_policy.py` | `9ac2209fbf963a456e155a6099eaee280896e1fe098110c1cb6158e758a6eebe` |
