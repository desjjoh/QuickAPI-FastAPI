# Graceful shutdown

[Documentation index](../README.md#documentation)

## Supported entrypoint

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

## Configuration

| Setting | Default | Validation |
| --- | --- | --- |
| `HTTP_DRAIN_TIMEOUT_MS` | `25000` | Integer 1–2147483647 |
| `SHUTDOWN_TIMEOUT_MS` | `30000` | Integer 1–2147483647; greater than HTTP drain budget |

Process environment overrides `.env`; omitted settings use code defaults. Blank,
fractional, boolean, negative, and out-of-range values are invalid. The overall
budget begins when shutdown starts, rather than restarting at each cleanup step.

Local Compose gives the API 35 seconds to stop, allowing the default 30-second
application budget to finish. If changing the application budget, configure Docker
or the hosting supervisor's termination grace to exceed it. A shorter external
grace period can kill the process before application cleanup finishes.

## Order and ownership

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
6. A completed, successful shutdown logs `Application exited cleanly`. Failed startup,
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

## Mutation boundaries

Draining allows accepted work to complete; it does not replay mutations. A cancelled
or forcibly terminated operation can have an uncertain outcome, especially around
commit. Request timeouts and database disposal do not prove rollback. Transaction
ownership, pre-commit activity checks, and commit uncertainty follow the
[mutation contract](transactions.md#expiry-and-commit-outcomes). Owned mutation tasks
remain tracked after their HTTP timeout or disconnect; drain cancellation and the
final watchdog still bound shutdown. Streaming already in progress is not replaced by a second JSON
response when interrupted.

## Verification

```powershell
python -m pytest -q tests/unit/common/handlers/test_request_work.py tests/unit/common/handlers/test_http_server.py tests/integration/test_shutdown_process.py --no-cov
python -m scripts.test_db test --layer integration
```

Process tests use isolated fixtures and test-only routes. They exercise idle stop,
an accepted database mutation, streaming, client disconnect, timed-out work that
continues cleanup, uncooperative handlers, a blocked event loop, cleanup failure,
stuck cleanup, and repeated stop requests. MySQL selection checks persistence after
the child exits. Marked transaction cases combine a real write, HTTP timeout and
shutdown: released work rolls back before dependency cleanup; work that ignores
cancellation reaches the final failure deadline. Both verify that the original
MySQL server session disappears. Unit checks cover diagnostic-write failure for
both forced-exit paths. Linux additionally qualifies real SIGTERM against production and
development-reload entrypoints. Windows uses a file-triggered programmatic stop for
process tests; these are not represented as POSIX signal or console-event evidence.

These tests do not install fault routes in the production application. Dated results
and platform limitations are in [Verification](verification.md).
