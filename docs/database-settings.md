# Database capacity and transport

[Documentation index](../README.md#documentation)

## Defaults and configuration

`DATABASE_URL` selects the database. MySQL uses `mysql+asyncmy`; SQLite uses its
existing asynchronous driver. Optional settings have code defaults and process
environment overrides `.env`. Explicit tests select their own configuration.

| Setting | Default | Accepted values |
| --- | --- | --- |
| `DB_POOL_CONNECTION_LIMIT` | `10` | Integer 1–1000 |
| `DB_POOL_QUEUE_LIMIT` | `50` | Integer 0–10000 |
| `DB_POOL_ACQUIRE_TIMEOUT_MS` | `1000` | Integer 1–2147483647 |
| `DB_CONNECT_TIMEOUT_MS` | `10000` | Integer 1–2147483647 |
| `DB_SSL` | `false` | Literal `true` or `false` |
| `DB_SSL_CA_FILE` | Omitted | Nonempty readable PEM CA path; requires `DB_SSL=true` |

Blank, fractional, negative, boolean-as-number, and malformed values fail validation.
TLS requires MySQL. Invalid CA files fail configuration rather than weakening
verification. Relative CA paths resolve from the command's working directory.
MySQL URL query options are limited to `charset`; connection/TLS policy cannot be
overridden through driver query options. Restart after configuration changes.

Application startup, readiness queries, Alembic commands, and disposable MySQL
fixtures use the shared engine factory. Migration helpers using an existing
connection inherit that connection's policy. SQLite does not receive MySQL pool or
TLS arguments and retains its existing pool behavior. Independent test-only SQLite
engines remain private compatibility fixtures.

## Connection and waiting limits

Each MySQL engine has a fixed native SQLAlchemy pool with `max_overflow=0`.
Connecting and checked-out leases consume admission slots. Once those slots are
occupied, at most `DB_POOL_QUEUE_LIMIT` callers wait in FIFO order. Zero means
immediate rejection when no slot is available. Queue capacity is a caller count,
not SQLAlchemy's idle-connection count.

The admission adapter is isolated around SQLAlchemy's pool extension hooks; native
SQLAlchemy still owns connection records, transactions, invalidation, and return.
Dependency upgrades must rerun the pool/socket tests. These are per-engine limits:
workers, replicas, CLI processes, and additional engines have independent budgets.
The configuration is not a global MySQL connection allocation or an OS capacity
guarantee.

Expired/cancelled waiters are removed. A slot transferred immediately before
cancellation is returned. Disposal rejects queued callers; checked-out connections
close when returned. Engine recreation retains the configured limits. This does
not implement application-wide request draining or cancel SQL on active leases.

## Deadline boundaries

Acquisition starts before admission and includes queue wait, new connection setup,
and SQLAlchemy's initial connection preparation. A separate connection deadline
covers asyncmy TCP/DNS setup, MySQL greeting/authentication, TLS negotiation, and its
session setup. During a new connection attempt, the earlier deadline wins.

The pinned driver's TCP-only timeout is supplemented by the full async connection
deadline. Cancellation closes the unfinished driver's connection; socket tests
verify peer disconnect and admission recovery. A connection is not handed to a
caller after the supported driver's acquisition is cancelled.

Neither deadline is a query execution/transaction deadline. Existing HTTP response
timeouts have their own scope. No automatic retry or cancellation of a committed
or already-running mutation is implied.

## Errors and privacy

Admission exhaustion, acquisition expiry, connection setup failure/deadline, and
closed-pool admission raise a controlled exception. HTTP clients receive status
503 with the existing `{status,message,timestamp}` envelope and message
`Database temporarily unavailable.` Driver details, SQL, credentials, and CA paths
are not returned. Internal safe diagnostics allow these codes:

`DB_POOL_CAPACITY`, `DB_POOL_ACQUIRE_TIMEOUT`, `DB_CONNECT_TIMEOUT`,
`DB_CONNECTION_FAILED`, `DB_POOL_CLOSED`, and `DB_TLS_REQUIRED`.

Ordinary SQL execution/constraint failures retain their existing behavior; this
policy does not turn every database exception into a capacity response.

## TLS verification

Local development/test MySQL can remain plaintext with `DB_SSL=false`. To enable
verified transport:

```dotenv
DB_SSL=true
DB_SSL_CA_FILE=/path/to/trusted-mysql-ca.pem
```

Omit the CA path to use system trust. The client requires a valid certificate chain,
matching DNS hostname or IP subject alternative name, and TLS 1.2 or newer. Unlike
the sibling Node driver policy, Python can verify an IP SAN; it does not bypass
identity verification for IP addresses. The connection is checked for an active
TLS cipher before admission to SQLAlchemy. There is no insecure verification switch
or fallback to plaintext when TLS is enabled.

### Windows entrypoints

The pinned asyncmy TLS socket upgrade fails with Windows' default Proactor loop.
When TLS is enabled, `python -m app.main` and built-in migration commands select a
selector loop. Non-TLS behavior retains the platform's normal loop selection.
Custom Windows asyncio callers must use the compatible loop, for example:

```python
from app.config.event_loop import run_database

run_database(your_database_coroutine())
```

For an external Uvicorn command use the application's loop constructor as well as
its proxy policy:

```powershell
python -m uvicorn app.config.application:app --loop app.config.event_loop:server_loop_factory --no-proxy-headers
```

The selector loop has platform limitations; large-scale capacity is not established
by local Windows verification. Linux keeps normal Uvicorn loop selection.

## Verification commands

```powershell
python -m pytest -q tests/unit/config/test_database_transport.py tests/integration/database/test_database_capacity.py --no-cov
python -m scripts.test_db test --layer integration
python -m scripts.test_db tls
```

The TLS command generates a temporary CA/server key, starts the independent
`quickapi-fastapi-tls-test` project on loopback port 3312 (optional `TEST_TLS_PORT`),
and removes that project and certificates afterward. It never rotates development
server certificates. Tests verify trusted encryption, wrong CA, wrong identity,
stalled TLS negotiation/socket closure, and native API startup/readiness with TLS.
Logs are retained under ignored `test-artifacts/` for CI diagnostics. Generated keys
are test-only and are not deployment material.

TLS cases use the explicit `database_tls` marker and are deselected from ordinary
compatibility runs. They run through the dedicated command, including in the
existing MySQL integration CI job; absent test infrastructure is a failure for
that command, not a silent skip.

Results and source identities are in [Verification](verification.md).
[Readiness and recovery](database-lifecycle.md) defines probe ownership, caching,
outage detection, and connection retirement. Deployment CA/DNS,
certificate rotation, and fleet capacity require hosting-specific verification.

Implementation references: [SQLAlchemy pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
and [Python TLS contexts](https://docs.python.org/3.12/library/ssl.html#ssl.create_default_context).
