# Database readiness and recovery

[Documentation index](../README.md#documentation)

## Contract

Startup verifies the committed Alembic revision using the application engine.
Migrations are applied only by explicit migration commands. After startup,
`/ready` checks connectivity through the same pool used by item operations.
`/health` reports process liveness without consulting MySQL.

The public readiness response retains `ready`, `status`, and `timestamp`. Database
errors, connection details, and dependency timings are not exposed. Probes work
when documentation, metrics, and diagnostics endpoints are disabled.

## Configuration

These optional settings use code defaults; process environment overrides `.env`.

| Setting | Default | Accepted values |
| --- | --- | --- |
| `DB_READINESS_TIMEOUT_MS` | `1000` | Integer 1–2147483647 |
| `DB_READINESS_CACHE_MS` | `1000` | Integer 0–2147483647; zero disables caching |
| `DB_MIGRATION_CHECK_TIMEOUT_MS` | `5000` | Integer 1–2147483647 |

Empty, fractional, negative, and malformed values fail startup validation. The
settings apply to the supported MySQL transport. [Transport settings](database-settings.md)
separately bound MySQL acquisition and connection establishment.

## Startup

Migration verification has a deadline covering connection acquisition and revision
inspection. A missing, incompatible, or unavailable revision history prevents
startup. Timeout, cancellation, or verification failure disposes the engine before
the failure propagates. The failing service owns this cleanup because it has not
yet joined the lifecycle handler's successfully started services.

Verification does not apply migrations, create missing history, or repair schema
drift. A failed initial startup requires another application start after the
problem is resolved. Runtime recovery does not rerun startup migration checks.
The asynchronous deadline does not preempt synchronous filesystem/CPU work.

## Runtime probes

Checks run on demand; there is no background monitor or retry loop.

1. A stopped database service reports unavailable without opening a connection.
2. Callers share an active probe, including its acquisition and cleanup. Cancellation
   of one caller does not cancel the shared operation.
3. Otherwise, a cached result is reused until its monotonic expiry. Both successful
   and unsuccessful results are cached.
4. A new probe acquires one application-pool lease and executes `SELECT 1`. Its
   deadline covers acquisition, SQL, and normal connection return.
5. Success permits readiness 200 when startup and other dependencies are healthy.
   Failure or timeout produces readiness 503. Successful leases are returned; a
   failed or cancelled active probe invalidates only its own connection.

The lifecycle handler retains its independent one-second dependency timeout. If
configured readiness work takes longer, a caller can receive an unavailable result
while the single shared probe finishes. Further callers cannot accumulate probes
behind that operation. Cleanup remains owned until completion. Python cancellation
is cooperative; real-driver tests establish the supported MySQL behavior.

## Outages and recovery

A connectivity failure does not dispose the shared application pool or restart the
API. Failed/stale probe connections are retired; later checks can acquire replacement
connections after cache expiry. A stalled connection is invalidated on cancellation
so unread protocol data cannot be reused. Other requests' leases are unaffected.

Cached success can briefly report readiness during an outage. Detection time includes
the remaining cache lifetime, probe deadline, deployment polling interval, and failure
thresholds. Readiness is evidence of current connectivity, not a guarantee that the
next business operation will succeed. Business requests are not automatically retried,
and a failed in-flight mutation is not replayed automatically. A caller can reconcile
an uncertain keyed result through [durable mutation retries](idempotency.md).

Stopping the database service clears the cache, cancels and awaits its active probe,
then disposes the engine. Readiness remains unavailable afterward. This does not
provide application-wide traffic withdrawal, mutation draining, or a final shutdown
deadline; those are separate lifecycle requirements.

## Verification

```powershell
python -m pytest -q tests/unit/common/handlers/test_database_readiness.py --no-cov
python -m scripts.test_db test --layer integration
```

The regular disposable MySQL suite includes a real HTTP listener and a test-owned
TCP relay. It verifies repeated outages and recovery on the same running API,
independent liveness, stale-session replacement, stalled-query connection retirement,
concurrent probes, exhausted acquisition cleanup, and ordinary item reads after
recovery. It does not stop or reconfigure the development database. The MySQL
socket test runs in the normal integration suite, without a database-backend skip.
Dedicated TLS tests retain their separate infrastructure and command.

Readiness does not qualify deployed database failover, backups, ingress behavior,
or TLS certificate rotation. Dated results are recorded in [Verification](verification.md).
