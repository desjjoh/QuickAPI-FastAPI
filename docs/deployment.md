# Deployment and operations

[Documentation index](../README.md#documentation)

The repository supplies local Compose, immutable-image qualification, release,
and disposable rollback tooling. A hosted environment must provide ingress,
secrets, storage, rollout policy, and operational ownership. Local Compose is not
a complete hosted production definition. See [Backlog](backlog.md) for remaining
qualification work.

## Production container validation

The runtime uses the digest-pinned Python 3.12 Trixie base declared in the
Dockerfile. Builder and runtime share that base. Only the builder installs
`build-essential`; runtime requirements live in `/opt/venv`. The API and migration
command run as UID/GID `10001:10001`, with root-owned application code and
dependencies. Application logging uses standard output and needs no writable
application directory. Compose readiness probes use Python's standard-library
HTTP client with a two-second timeout and explicit proxy bypass. Curl and its
additional dependencies are not installed in the runtime stage.

Both build stages apply available Trixie package updates. The builder installs
the Dockerfile's pinned `PIP_VERSION` in `/opt/venv`; the runtime removes the base
image's separate pip installation before copying that environment. The active
runtime pip remains available for dependency consistency checks. Review installer
pin updates alongside requirements and qualify the resulting final image in CI.

### Updating the Python base

1. Select a supported Python 3.12 patch tag with the same Debian variant. Inspect
   its official registry manifest with
   `docker buildx imagetools inspect python:<patch>-slim-trixie`.
2. Update the Dockerfile's `PYTHON_IMAGE` tag and index digest together. Retain the
   digest in source control; changing a moving tag alone does not update the base.
3. Submit the update through CI. Require a fresh image build and the runtime
   identity, permissions, dependency, migration, HTTP/MySQL and shutdown checks.
   Review the candidate security scan results; the security gate is required.

The base digest fixes the base artifact, not packages downloaded later by apt or
pip. Dependency requirements remain manually pinned; this does not promise
byte-for-byte reproducible builds. Do not override `PYTHON_IMAGE` in a release
build without reviewing and recording the selected source change.

### Qualifying the image

Build and qualify the runtime artifact against independent disposable MySQL:

```powershell
docker build -t quickapi-fastapi:local .
python -m scripts.test_image --image quickapi-fastapi:local
```

The command loads guarded `.env.test` credentials and creates the
`quickapi-fastapi-smoke` Compose project. It publishes no host ports and mounts no
development data. It waits for MySQL, applies migrations using the built image,
starts that image with production defaults, and checks CRUD, readiness/liveness,
favicon delivery, and disabled documentation/diagnostics/metrics. It also runs
non-root identity, code/dependency permissions, development/build-tool exclusion
and `pip check` checks, sends Docker's stop signal, and verifies exit zero and the final clean
shutdown record. Bounded logs are retained in `test-artifacts/production-mysql.log`;
the temporary project and storage are removed on completion or failure.

The check also creates a keyed item and updates it before stopping the API. It
replaces only the API container, verifies a new container identity with the same
image ID and unchanged MySQL container, and waits for readiness. The replacement
must return the retained item fields/version, replay the original create status
and exact response bytes without changing the item or collection, and accept a
fresh update and deletion. Both API instances must stop cleanly; logs from the
first instance are preserved before replacement.

This validates the selected local image and MySQL behavior. A local tag is not an
immutable release reference. Persistence is qualified across API container
replacement while the disposable MySQL container stays running. Its temporary
storage does not qualify database restarts or durable database volumes. Deployment storage, representative
future migrations, restore, failover, and release promotion have separate acceptance
criteria. The test database is disposable and is not a deployment configuration.

## Operational endpoints

FastAPI's lifespan starts registered services before the app becomes ready. The
database service checks its Alembic revision, readiness requires startup completion
and healthy registered services, and shutdown stops only successfully started
services in reverse order. Partial startup failure rolls back already-started
services. The unversioned operational surface is shown below. `/info` and `/system` require
`DIAGNOSTICS_ENABLED`; `/metrics` requires `METRICS_ENABLED`. Both flags default off
in production, and enabling them supplies no authentication.

| Route          | Purpose                                                                 |
| -------------- | ----------------------------------------------------------------------- |
| `GET /`        | Friendly API greeting.                                                  |
| `GET /health`  | Process liveness only; it deliberately does not query dependencies.     |
| `GET /ready`   | Startup completion and health of every required registered service.     |
| `GET /info`    | Public application identity, process, Python, and platform metadata.    |
| `GET /system`  | Bounded host, process, event-loop, and database diagnostics.            |
| `GET /metrics` | Prometheus plaintext exposition using its full negotiated content type. |

Liveness and readiness are intentionally different. A failed liveness probe means
the process should be restarted. A failed readiness probe returns HTTP 503 and
means the running process should temporarily receive no application traffic. Readiness still performs bounded dependency checks internally, but its public
response omits dependency names/timings in every environment. `/system` retains its
existing `db` summary when diagnostics are enabled. See the
[public probe contract](security.md#operational-access).

## Metrics and request outcomes

The schema matches QuickAPI-Express and QuickAPI-NestJS, with Express's separate
abort counter:

| Metric                        | Labels                      | Meaning                                                                                                 |
| ----------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------- |
| `http_requests_total`         | `method`, `route`, `status` | Completed responses, including emitted 4xx/5xx and pre-header timeout 408                               |
| `http_request_duration_ms`    | `method`, `route`, `status` | Completed-response duration in milliseconds; buckets 5, 15, 50, 100, 250, 500, 1000, and +Inf           |
| `http_requests_aborted_total` | `method`, `route`           | Incomplete responses: disconnect, stream timeout, cancellation, or failure without a completed response |

`route` is the full declared template, for example `/api/v1/items/{id}`, including
declared mount prefixes. Missing routes and rejections before routing use
`<unmatched>`; unsupported methods use `<other>`. Labels never contain raw item IDs,
unknown URLs, queries, client addresses, or request IDs. The five root operational
paths `/health`, `/ready`, `/info`, `/system`, and `/metrics` remain excluded from
all three traffic metrics. Their access logs are still emitted.

One shared per-request observation feeds access logs and metrics exactly once.
Completion is the final response body accepted by ASGI send, not return from the
handler, dependency cleanup, or background work. An observed disconnect/send failure,
external cancellation, or owned streaming deadline ends an incomplete response.
A started 200 that is truncated is an abort, never a completed 200 or a fabricated
499/0 response. The observation retains a status only when headers were accepted;
aborts have no status metric label. Late cleanup, failures, or attempted output do
not change the recorded outcome. The observer adds no receive-reader task; it uses
the timeout middleware's existing disconnect observation and ASGI channel wrappers.
These are server-side transport observations, not proof the peer consumed every byte.

Dashboard queries use the `route` label and millisecond duration thresholds.
Histogram grouping/filtering includes `status`; `_bucket`, `_sum`, and `_count`
series derive from `http_request_duration_ms`. Completed-response histograms exclude
aborted requests, which are measured by `http_requests_aborted_total`.

## Logging

### Output and levels

`ENV` selects presentation: development/test use single-line console output;
production uses JSON records with UTC ISO timestamps. `LOG_LEVEL` accepts `DEBUG`,
`INFO`, `WARN`, or `ERROR`, defaults to `INFO`, and filters both application output
and the standard logging bridge. There is no separate output-format setting.

| Event                                        | Python level |
| -------------------------------------------- | ------------ |
| Successful request access record             | DEBUG        |
| Boot, listening server and successful exit   | INFO         |
| Service registration, start/stop and timings | DEBUG        |
| Expected client rejection / aborted request  | WARNING      |
| Server error / unexpected failure            | ERROR        |
| Fatal initialization/runtime failure         | CRITICAL     |

At INFO, successful request logs are hidden while lifecycle messages are visible.
The boot banner is emitted at the start of application construction, before lifecycle
service registration. The lifespan starts registered services; the supported server
entrypoint emits the HTTP startup message only after Uvicorn starts the listener.
Construction or a standalone ASGI lifespan does not claim a listening server.

Lifecycle messages follow the Express/NestJS conventions: `Starting services…`,
`Service started → <name>`, `All services started in <duration>ms`, then the HTTP
startup message. Shutdown logs `<signal> received — initiating shutdown` immediately
when a signal is handled, or `Shutdown requested — initiating shutdown` for a
programmatic stop. Each stop logs `Service stopped ← <name>`, followed by
`Shutdown completed in <duration>ms` and `Application exited (code 0)` after successful
runner cleanup. The initiation notice is emitted once; standalone lifespan cleanup
uses the programmatic wording. Failed runs never receive the successful exit record.
Python severity names, runtime identity and actual service names remain native.
Metrics and request-outcome observation are independent of log filtering. There is
one access record per settled response outcome; a rejection/failure can also have a
separate fixed diagnostic event. An aborted response whose headers carry a server
error status uses ERROR.

Console layout is `timestamp [pid] [level] [request-id] message`, with the request ID
when available. Console timestamps use local time. Control characters in messages
and context fields are escaped to keep a single record per line. Production output
has no ANSI styling and uses ASCII-compatible JSON escaping, including for Unicode
values; JSON consumers recover the original string values normally.

### Structured records

Production records use `time`, `pid`, `hostname`, `levelLabel`, and `msg`. Supported
context/outcome fields are `requestId`, `method`, `ip`, `route`, `status`, `durationMs`,
`outcome`, and `headersSent`. Status is absent when response headers have not been
accepted. Duration uses milliseconds. Methods and declared route templates follow
[the outcome contract](deployment.md#metrics-and-request-outcomes).

Request correlation is preserved for concurrent requests and final server errors
after request-context cleanup. Raw paths are not bound to logging context. Generic
logger callers must use fixed, safe messages and declared route templates; allowed
metadata fields are not a place to embed request/provider data.

### Server, dependency, and bootstrap output

Standard logging records pass through a privacy-safe handler. All dependency records
use a WARNING minimum and the configured output threshold, including unlisted file
watcher loggers and children that explicitly enable DEBUG. Application DEBUG output
remains independent of this floor. Original dependency message
text/format arguments are never formatted into application output: records use
`Dependency log event.` or `Server event.`, plus safe exception diagnostics where
available. Uvicorn access output is disabled because application outcomes own access
logging. Python warnings are routed through standard logging.

In development, Uvicorn's reloader uses `watchfiles.main`, which can emit DEBUG
events such as `2 changes detected: ...` before Uvicorn filters the changed paths.
An event can describe a non-Python file that does not trigger a reload; matching
Python changes can trigger one. These are routine filesystem notifications, not
warnings or evidence of application failure, and the dependency WARNING floor
suppresses them. The generic dependency message is supplied by this application's
handler, not by Watchfiles. Because it discards the original logger name and message,
an existing generic line alone cannot identify its source or the changed files;
diagnosis requires a controlled capture of the original record.

Configuration errors are reported before the logger can be constructed. They identify
invalid/missing field names without echoing supplied values or exception messages.
Production emits a critical JSON bootstrap record; development/test show a readable
field list. Fatal server initialization uses a fixed critical event with safe
exception diagnostics and exits with code 1. Console output supports restricted
Windows pipe encodings without exposing a chained validation exception.

The logging contract covers application-owned logging and standard records routed
through this configuration. External process output and libraries that install their
own output handlers need independent integration controls. Retention, log access,
shipping, and alerting belong to the consuming deployment.

## Graceful shutdown

### Supported entrypoint

Use `python -m app.main` for coordinated shutdown. The container uses this command.
The entrypoint owns a narrow Uvicorn server integration and its signal handling;
development reload uses Uvicorn's supervisor and watches Python files under `app/`.
Each application worker owns its shutdown state and deadline.

A stop received while startup is finishing also closes resources that completed
startup after the stop request. Startup completion does not reopen admission after
shutdown has begun.

Running plain `uvicorn app.config.application:app` bypasses the early signal hook
and final watchdog. ASGI lifespan cleanup still runs, but that command does not
provide the complete shutdown contract described here. Multi-worker orchestration
and hosted traffic withdrawal require their own deployment qualification.

### Order and ownership

1. On a handled shutdown signal or graceful programmatic stop, mark the lifecycle
   unready and close application HTTP admission immediately.
2. Uvicorn closes listeners and idle connections. Requests that reach closed
   application admission receive the usual error envelope, status 503, message
   `Application is shutting down.`, and `Connection: close`. This applies to probe
   paths too; connections may instead be refused after listener closure.
3. Accepted requests continue within the drain budget. Database admission remains
   available to them. The application tracks HTTP handlers and the timeout
   middleware's child tasks through actual completion, including dependency cleanup.
   Response completion, disconnect, or a timeout response is not proof that work ended.
4. On drain expiry, cancel outstanding work and retain ownership while cancellation
   and transaction cleanup settle. Do not dispose dependencies under active handlers.
5. Stop registered services in reverse order. Database shutdown stops its shared
   readiness probe and then disposes the engine. Cleanup failures are recorded;
   remaining services still receive their stop call.
6. A completed, successful shutdown logs `Application exited (code 0)`. Failed startup,
   failed draining, or failed cleanup does not receive that success message.

Repeated shutdown signals request immediate failure termination. A thread watchdog
enforces the overall budget independently of the asyncio event loop, including its
final task cleanup. On expiry it writes a fixed diagnostic and exits with status 1.
Failure to write the diagnostic, including a closed stderr or broken pipe, cannot
prevent forced termination. The repeated-signal path uses the same exit boundary.
The watchdog cannot replace an external supervisor for a process frozen in native
code that prevents Python threads from running, or an OS-level failure.

The supported server restores prior signal handlers after handling shutdown, then
finishes event-loop task cleanup before logging success and returning exit zero.
Failed or forced shutdown uses status 1. Logs and database outcomes are part of verification,
not just the exit code. Windows `terminate()` is a hard kill; graceful programmatic
stop and supported console signal handling are different operations.

### Mutation boundaries

Draining allows accepted work to complete; it does not replay mutations. A cancelled
or forcibly terminated operation can have an uncertain outcome, especially around
commit. Request timeouts and database disposal do not prove rollback. Transaction
ownership, pre-commit activity checks, and commit uncertainty follow the
[mutation contract](architecture.md#mutation-transactions). Owned mutation tasks
remain tracked after their HTTP timeout or disconnect; drain cancellation and the
final watchdog still bound shutdown. Streaming already in progress is not replaced by a second JSON
response when interrupted.

## Transport deadlines

### Deadline contract

| Boundary             | Default    | Behavior                                                                                   |
| -------------------- | ---------- | ------------------------------------------------------------------------------------------ |
| `total_timeout`      | 10 seconds | From timeout-middleware entry until the final response body is successfully sent           |
| `first_body_timeout` | 5 seconds  | Maximum wait for the first requested body message                                          |
| `chunk_timeout`      | 2 seconds  | Maximum wait for each subsequent requested body message until the request body is complete |

Constructor budgets must be finite and greater than zero; invalid values fail
middleware construction. The overall deadline applies when the handler never reads
a body. Body-receive deadlines do not apply to the disconnect wait after the final
request-body message.

Application settings provide optional environment overrides:
`REQUEST_TIMEOUT_MS=10000`, `REQUEST_FIRST_BODY_TIMEOUT_MS=5000`, and
`REQUEST_CHUNK_TIMEOUT_MS=2000`. Milliseconds convert to seconds at middleware
construction. Both body-wait budgets must not exceed the total. See
[HTTP configuration](configuration.md#browser-and-http-settings) for ranges, defaults, and source precedence.

ASGI receives a scope after HTTP headers have been parsed. `first_body_timeout` is
a body-message deadline, not slow-header protection. Server/ingress header-receive
protection requires separate configuration. The response deadline starts at timeout
middleware entry, not TCP acceptance, and does not cover outer middleware rejections.

### Server and ingress boundary

Application response deadlines do not establish transport parity with Express's
HTTP server receive deadlines. ASGI delivers the request scope after header parsing;
the application cannot time incomplete headers that have not reached it. Body-read
deadlines apply when downstream code requests body messages, not to an independently
enforced maximum duration for receiving the entire upload. Keep-alive timing governs
idle connection reuse and does not replace either protection.

The selected server/ingress must enforce bounded header-receive and whole-upload
durations. If those guarantees depend on ingress, direct application-port access
must be restricted so clients cannot bypass them. Hosting verification must exercise
slow/incomplete headers and stalled/trickled uploads over real connections, including
the direct-port restriction, and retain evidence of timely rejection or closure and
successful normal requests afterward. An early transport rejection may close the
connection without the application's JSON error envelope or request ID.

Hosted qualification is tracked in [Backlog](backlog.md#hosted-deployment-qualification).
Application and loopback tests do not qualify an undeployed ingress. No ineffective
header-receive environment setting is exposed for the current Uvicorn entrypoint.

### Response and error behavior

- Normal completion retires the response deadline. Dependency/background cleanup after the final response body does not change an already-completed response.
- Expiry before headers returns exactly one 408 with the `{ status, message, timestamp }` envelope. Total expiry uses `Application response deadline exceeded.`; body waits identify first-body or chunk expiry. A timeout preserves CORS policy already established for the request, along with outer security and correlation headers. Expiry before CORS validation does not grant browser permission. HEAD retains the status and representation headers without body bytes.
- Expiry after headers raises a dedicated internal stream-abort error. Uvicorn closes the incomplete HTTP response; there is no replacement JSON/408 and no synthetic final chunk that would falsely mark the stream complete. A client can observe its original status and partial bytes followed by an incomplete-body/connection error. Uvicorn/the outer error boundary may log the exception even though the wire contains no 500 response.
- Late sends are suppressed after expiry, disconnect, or response completion. Downstream exceptions, including unrelated `TimeoutError`, follow normal exception handling. External server cancellation propagates rather than being converted to 408.
- Explicit ASGI disconnects and transport `OSError` close the sending boundary and mark the request abandoned. Unmarked handlers receive cooperative cancellation; owned mutations retain their task until transaction cleanup settles. A receive-side `TimeoutError` is preserved, since its being an `OSError` subclass does not establish client disconnection.

### Body ownership and backpressure

One reader owns the server's receive channel and passes messages to the handler in order. Prefetch is bounded to one queued message and one in-flight message; the middleware does not accumulate an entire upload. Once the complete request has arrived, that reader can observe disconnects even if an ordinary handler never calls `receive()`.

For an ignored, incomplete multi-chunk upload, prefetch backpressure can delay disconnect observation until body messages are consumed. The middleware does not drain/discard arbitrary uploads to look for a disconnect; the overall response deadline still bounds the sending window. Other body-size and server receive policies retain their own responsibilities.

### Cancellation and cleanup limits

The response deadline can finish the transport before owned mutation work or cancellation-resistant work settles. Middleware retains unfinished downstream tasks and retrieves late failures. Expected request-expiry rejection does not produce an additional late-failure error record; unexpected late failures retain safe diagnostics. It does not cancel the same task again merely because cleanup is still running.

Cancellation is cooperative. It cannot force a blocked event loop, stop synchronous thread work, prove SQL cancellation, or guarantee rollback. Async resource owners must make cleanup cancellation-safe. In Starlette's AnyIO streaming cancel scopes, cleanup awaits may require a shielded cancel scope; arbitrary unshielded async generator cleanup cannot be guaranteed to finish by this middleware.

Retained tasks participate in [graceful shutdown](deployment.md#graceful-shutdown). Marked mutation
routes use the separate [transaction owner](architecture.md#mutation-transactions) through response
preparation and commit, checking activity before work, after delayed acquisition,
and immediately before commit. Successful delivery of a 408 does not establish
whether a concurrent mutation committed. An already-started COMMIT can succeed;
the transaction guide defines these uncertainty boundaries and retry limitations.

## Releases and rollback

### Source and version

Automatic releases follow successful **push** runs of `Quality` on `main` in this
repository. Pull-request and fork runs cannot authorize publication. The selected
commit must belong to main, and its latest push CI run/attempt must be completed,
successful and contain exactly one successful `Deployment gate`. The workflow
checks this through GitHub's API before building and again before registry login.

[VERSION](../VERSION) defines the release version and must match `APP_VERSION` in
[.env.example](../.env.example). Change both when preparing a new version and keep
local `.env` settings/comments synchronized as usual. Application `APP_VERSION`
remains runtime configuration; release qualification supplies the tracked version
to its API and migration containers through the tooling-only `SMOKE_APP_VERSION`.
The image's source, revision and version labels must match the selected source.

### Candidate and evidence

Buildx produces one linux/amd64 OCI archive with SPDX SBOM and maximum-detail
SLSA provenance. The containerd image store allows qualification of that candidate
without rebuilding. Publication retains the complete OCI index and its attached
attestation manifests.

The gate validates:

- OCI descriptor sizes and SHA-256 blob digests, including runtime layers.
- One runtime platform, exact source/version labels and unambiguous attestations.
- Attestation manifest/statement bindings, provenance repository/commit and an
  SPDX inventory containing every declared runtime Python package/version.
- The same loaded candidate's non-root identity, permissions, dependencies,
  migrations, MySQL CRUD/probes, API replacement, persistence, replay and shutdown.
- A fresh Trivy scan of the candidate's OCI layout with OS and Python inventories,
  using the shared [critical-only security policy](security.md).
- Hash-bound source, smoke result/log, raw scan, decision, SBOM and provenance.

Legacy BuildKit attestation manifests and OCI artifact subject binding are
supported. An empty statement subject relies on the enclosing manifest's verified
runtime binding; any supplied subject must identify that runtime. Unsupported or
ambiguous metadata fails qualification. These are validated build attestations,
not a claim of independent signing or a particular SLSA certification level.

Verification re-evaluates the current exception policy and checks evidence hashes
before publication. Failed attempts, modified files/archives, changed policy,
expired exceptions, scans older than 24 hours and invalid image identities block
publication. The allowed clock tolerance is five minutes into the future.

Temporary OCI layouts, registry data and login files are outside artifact uploads.
Reports, extracted attestations, identity records and failure diagnostics are
retained for 90 days. The original archive is not uploaded as a workflow artifact;
after publication, the registry retains the image and attached attestations.

### Registry rehearsal and publication

Every release, including a dry-run, exercises the publication implementation
against a fresh loopback-only temporary registry. It imports the archive, creates
commit/version tags, checks both digests, downloads the complete OCI layout and
validates the runtime and attestations again. Registry containers and temporary
storage are removed on success or failure.

Registry-exported OCI layouts may catalog additional referrers or aliases. The
round-trip check selects the independently approved candidate digest, rejects a
missing digest or conflicting descriptors, and verifies its full runtime and
attestation graph. The original build archive still requires exactly one root
candidate. `roundtrip-index.json` retains the returned catalog for diagnostics.

A real registry login occurs only after qualification, rehearsal and the final
source/evidence recheck succeed. The publisher imports the original OCI archive;
there is no second build. It verifies tag digests and the downloaded OCI layout,
then records `publication.json` and `release-image.env` containing:

```text
QUICKAPI_IMAGE=ghcr.io/owner/repository@sha256:<verified-index-digest>
```

Tags use the full source SHA and tracked version, matching Express. Tags can move;
the canonical immutable reference is the image index digest. Failed publication
can leave registry content or partially updated tags, but does not produce an
approved deployment reference. Preserve evidence and use a fresh qualified attempt
to retry; never promote incomplete evidence or bypass the gate.

Defaults use `ghcr.io/<lowercase-owner>/<lowercase-repository>` with the workflow's
GitHub token. Repository variables `CONTAINER_REGISTRY` and `CONTAINER_REPOSITORY`
can select another destination; use `REGISTRY_USERNAME`/`REGISTRY_PASSWORD` secrets
when the destination needs them. The `release` GitHub environment can apply the
repository's approval and branch restrictions. GHCR package permissions must allow
this repository's workflow to publish.

Trivy, regctl and disposable registry tool images are pulled, resolved to immutable
IDs and used by those IDs. Publisher credentials are mounted read-only through a
self-contained Docker login configuration. Host credential helpers are unsupported.
No scanner/publisher receives the Docker socket. No new application environment
settings or production requirements are introduced.

### Running a dry-run

1. Make the workflow/tooling available on the repository's default branch and main.
2. Obtain successful main-branch push `Quality` CI for the full source commit SHA.
3. Open **Actions → Release image → Run workflow**, select **main**, paste that
   commit into `git-ref`, and leave **dry-run** enabled.
4. Inspect the retained source, candidate, smoke, security and registry-test records.
5. For real publication, use an authorized run with dry-run disabled, or the
   automatic successful main push flow. Confirm `publication.json` and the digest
   reference; a dry-run does not publish to GHCR.

Each run builds and qualifies its own candidate. A later publishing run does not
silently reuse a previous dry-run's approval. GitHub service availability and
registry permissions are prerequisites for hosted qualification.

### Retained-image rollback

Rollback selects an earlier **published image digest**. It does not rebuild that
source, move registry tags, reverse migrations or reset a database. Preserve
successful `publication.json` records and their source, SBOM/provenance, scan and
smoke evidence beyond CI retention when your rollback horizon requires it. Retain
the corresponding registry digests against deletion/garbage collection.

The application requires exact Alembic revision equality. An older image can be
considered for application-only rollback only when it expects the current single
schema head and the release pair passes compatibility qualification. Head equality
is necessary, not sufficient: business/data contracts and retry semantics also
have to remain compatible. Changes requiring another schema revision need their
own recovery plan; do not bypass readiness or stamp/downgrade the database to make
an image start.

#### Disposable qualification

The manual [Rollback qualification workflow](../.github/workflows/rollback-check.yml)
runs trusted main-branch tooling with registry read permission. Select both input
references from successful publication records: `current-image` is the image being
replaced and `rollback-image` is the earlier retained version. Use full
`repository@sha256:<index-digest>` references from this application's configured
registry/repository. Tags, identical references and same-source rebuilds are
rejected. Image source/version/user labels, pulled digests and both migration heads
are verified before any database is started.

1. In **Actions → Rollback qualification → Run workflow**, select **main**.
2. Paste the two retained image references into `current-image` and `rollback-image`.
3. Review `rollback-evidence-<run>-<attempt>`, including `result.json`, image/head
   identities, transition records, command diagnostics and API/MySQL logs.

The check owns `quickapi-fastapi-rollback`, publishes no API/database host ports and
uses temporary MySQL storage. It migrates a fresh database **once** with the current
image, then exercises current → rollback → current against that same running MySQL
container. A read-only live schema check precedes every API start. Each transition
replaces only the API and verifies its requested immutable image reference.

The current image creates/updates retained state and a keyed response. The rollback
image must read it, replay the original exact response without another mutation,
and update/create resources. Returning to the current image must preserve those
writes, replay the original response and accept further updates/deletion. All three
API instances must stop cleanly. Failure or cleanup failure leaves `passed: false`;
temporary project resources are removed and reports are retained for 90 days.

The command can also be invoked explicitly after installing development tooling
and preparing guarded `.env.test` configuration:

```powershell
python -m scripts.test_rollback --current-image 'ghcr.io/owner/repository@sha256:<current-digest>' --rollback-image 'ghcr.io/owner/repository@sha256:<retained-digest>' --source 'https://github.com/owner/repository'
```

Use registry login when image pulls require it. The workflow reuses release
registry variables/secrets. These are tooling settings, not application `.env`
configuration. Local verification normally uses
`python -m pytest -q tests/unit/config/test_rollback.py --no-cov`; live Docker/MySQL
rollback qualification stays in CI.

#### Applying a qualified rollback

Before a real application rollback, confirm the current database head, the
reviewed release pair's data compatibility and current security acceptance. A
compatibility test does not refresh an earlier vulnerability scan or independently
verify an operator's claim that a reference came from a successful release.
The current image is checked against current build-content rules. A retained
image is checked for its non-root runtime identity and application compatibility;
historical tool inventory, such as an older curl installation, does not by itself
invalidate that compatibility evidence. Security acceptance remains a separate review.

Withdraw traffic/admission and drain/stop the current API. Select the retained
verified digest in the deployment configuration, without running migrations, then
start it and verify readiness, representative reads/writes, retry behavior and
logs before restoring traffic. Keep the replaced digest and deployment record.
If the retained image fails compatibility/readiness, leave traffic withdrawn and
use the recorded current digest or a reviewed forward repair. Database restoration
and destructive schema reversal require separate qualification.

This repository exercises the image/database procedure in disposable infrastructure.
Hosting-specific traffic withdrawal, rollout and restore remain deferred. Qualify the actual historical release pair before relying on application rollback.
