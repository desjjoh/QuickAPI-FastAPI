# Verification report

[Documentation index](../README.md#documentation)

## Source and environment

Verified on 2026-10-30 against base commit
`61596ef5d5d2777bda85e90d5ea9e4b76dba4b22` and the local fingerprints below.
The candidate includes uncommitted changes; the base commit alone does not identify
it. This report describes the current MySQL-only application and tests. Earlier
verification snapshots remain in Git history and do not define current support.

Windows uses Python 3.12.10. Linux uses Python 3.12.16 with disposable dependencies
and read-only source mounts. Persistence tests use guarded disposable MySQL 8.4.6.
The development database is separate and was not modified.

## Results

| Check | Result |
| --- | --- |
| Windows full MySQL suite | 1144 passed; two POSIX-only cases skipped; five dedicated TLS cases deselected; 95.99% branch-measured application coverage |
| Linux full MySQL suite | 1146 passed; no skips; five dedicated TLS cases deselected; 96.07% branch-measured application coverage |
| Database-independent units | 728 passed with an unreachable configured database target; no database-backed fixtures selected |
| Dedicated TLS | Five cases passed on Windows against the separate generated-certificate MySQL server |
| Coverage gates | Middleware 97%, lifecycle 99%, database package 95%, API 99%; all configured gates passed on Windows and Linux |
| Formatting/linting | Combined Black/logical-spacing check: 173 files, zero changes on Windows/Linux; Ruff passed |
| Format enforcement | CI static analysis runs scripts.format_code --check; VS Code format-on-save uses the same formatter through Black Formatter; no additional Python dependency introduced |
| Type checking | mypy: 72 application/tool files passed; strict Pyright: affected Python files, zero diagnostics, using explicit installed typeshed |
| Dependencies | Local and fresh-image pip checks passed; removed optional database driver absent from both; pytest absent from runtime image |
| Transaction HTTP qualification | Existing 32-case preparation/ownership module and 23 real HTTP/MySQL expiry, uncertainty and rollback-loss cases pass in both full suites |
| Forced-exit diagnostics | Watchdog and repeated-signal paths terminate with status 1 even when stderr raises OSError or BrokenPipeError |
| Combined transaction shutdown | Expired marked mutations retain dependencies through rollback; cancellation-resistant mutations reach the final watchdog; original MySQL server sessions disappear |
| Final process assertions | Combined dependency-order/watchdog assertions pass in both full suites |
| Rollback connection loss | Real ROLLBACK command/acknowledgement loss invalidates the lease, preserves absence of the failed write, retires the server session and restores a queued caller on a replacement connection |
| Expiry and uncertain outcomes | Monotonic checks, expired acquisition without business SQL, caught cancellation, all four mutation methods after writes, real disconnects, held INSERT results, interrupted COMMIT, lost acknowledgement, confirmed commit before lost response, cleanup failure, invalidation and recovery |
| Transaction ownership | Four marked item mutation routes share one explicit request session; repositories never commit/roll back independently; read routes remain unmarked |
| Service boundary | Services return ORM results or plain typed system data; controllers assign awaited results to local variables and validate response models before returning them |
| Controller validation | Invalid outputs rejected for all six item operations, root greeting, health, runtime identity and nested diagnostics; pagination metadata preserved; transaction validation failures roll back MySQL writes |
| Service/session composition | Real MySQL dependency test proves the injected item service borrows the same active route-owned session as repeated get_session dependencies; completed owner cannot silently autobegin |
| Boundary guards | Existing owner/active factory session rejected; shared dependencies borrow without closing; completed owner cannot silently autobegin; streams/background tasks rejected and prepared error responses rolled back |
| Configuration | Application version 1.3.0 reflected in example/local environment, test configuration and smoke stack; only mysql+asyncmy accepted; tests remain independent of development .env |
| Migration behavior | Empty-schema rejection, baseline/model comparison, repeated upgrade, incompatible history, downgrade/reapply, offline SQL and real online commands pass against MySQL |
| Pool/session cleanup | Real MySQL late-connection disposal, queue/cancellation/invalidation, and server-session disappearance checks pass |
| Safety | Live identity checks, exclusive reset guards, destructive schema restoration, unavailable-target failure, and isolated command-lock tests pass |
| CI definition | Unit job, MySQL integration/E2E, full MySQL coverage, dedicated TLS and independent MySQL image qualification; YAML parses |
| Image-runner failures | Database startup, HTTP-check, and artifact-write failures all attempt disposable-project teardown |
| Built runtime image | sha256:97709d19dec42afd641abf3710170a2ad78c7ebfbb5de97ea5e359352f05ccbf |
| Built-image MySQL qualification | Explicit migration, CRUD, probes, favicon, production exposure defaults, pip check, Docker SIGTERM, exit zero and final success record passed |
| Cleanup | Generated TLS material, independent smoke/TLS projects and verification containers removed; existing development/regular test services retained |
| Hosted CI / branch enforcement | Not run / not independently verified for this candidate |

The initial Linux run had 1145 passes and one database fixture setup error: a new
connection exceeded the one-second acquisition deadline. A complete repeat after
the independent image/TLS jobs finished passed without application or test changes.
This records the observed local timing sensitivity rather than hiding the first result.

## Item contract evidence

The new exact-price module covers 55 unit cases; the new MySQL contract module
covers 62 cases. Evidence includes exact storage and numeric JSON round trips,
rejected POST/PUT/PATCH writes leaving data unchanged, non-finite input rejection,
inclusive fractional filters, accepted alphanumeric IDs, and controller validation
rolling back writes against invalid stored prices. OpenAPI records numeric/string
inputs and numeric outputs with camelCase response timestamps.

A local comparison against the actual Express price validator at commit
`eed860ca5d5d2549b6d7d1534063bfd54ff9b1bb` matched acceptance and normalized numeric
output for all 33 shared JSON-compatible cases. Node is not a FastAPI test dependency.

## Boundaries

All persistence fixtures use MySQL. No other database backend is selected or used
as a fallback. Unit tests use test doubles and do not require Docker. Direct full
pytest requires the disposable server to be started and migrated; the wrapper
manages that lifecycle and measures coverage. Dedicated TLS cases remain explicit
qualification with their own temporary server, rather than ordinary-suite passes.

Destructive migration cases hold the exclusive test guard and restore the baseline
before releasing it. Both schema fixtures and row-reset fixtures verify the permitted
live database/user. No migrations are applied automatically by application startup.
The schema is unchanged. Item JSON now uses camelCase timestamp aliases, IDs accept
ASCII letters and digits, and prices enforce exact two-decimal bounds. See
[API contracts](api-contracts.md). Repository callers own their transaction explicitly,
as described in [Mutation transactions](transactions.md).
Item and system controllers delegate application logic to services, then validate
the returned data into JSON response models, as described in
[Controllers and services](services.md). Transaction ownership and expiry/shutdown boundaries are retained.

Real constraint-rejection cases verify rollback after an earlier successful write.
Expiry tests hold actual MySQL protocol packets rather than simulating commit
results. Independent observer sessions distinguish uncommitted rows from rows
committed before an acknowledgement reaches the driver. Rollback barriers are armed
after initial connection setup so they interrupt rollback of an actual application
write. Combined process tests check that dependency teardown precedes service
cleanup and that stuck transaction work reaches the final watchdog, rather than
merely accepting any nonzero exit. After the Windows full run, only custom price
error punctuation was adjusted; 65 focused price/OpenAPI checks passed afterward.
The Linux qualification uses that final application source.
Coverage describes application code executed in the parent test process; it is not
an aggregate of native application or Alembic subprocess coverage. MySQL migration
DDL is not claimed to be transactionally reversible. The database-package threshold
passes with online-command behavior verified separately through real subprocesses.

The image check uses the built artifact, production settings and its own ephemeral
MySQL project without host ports or development volumes. It does not establish
restart/storage durability, deployed failover, backups/restoration, historical-image
rollback, release promotion, or real ingress behavior. Request expiry prevents
commit only before the final activity boundary. Packet-barrier tests demonstrate
that a COMMIT already initiated can succeed after HTTP timeout and that a lost
acknowledgement does not establish rollback. No SQL-cancellation or automatic retry
safety guarantee is made; forced termination retains uncertain outcomes.

The obsolete required contexts `test-layers (integration)` and `test-layers (e2e)`
are no longer emitted. Remove them from existing GitHub rulesets and retain the
MySQL checks listed in [Branch protections](branch-protection.md). Local success and
workflow definitions do not establish hosted check execution or ruleset enforcement.

## Input fingerprints

The Python tree digest for all 173 files under `app`, `tests` and `scripts` is
`714bb859dd0633bd435c10aabcba67bb1117f4b5d6389a779a091737e78e7967`. It hashes sorted project-relative POSIX paths, each followed
by a NUL byte, the raw file bytes and another NUL byte. The table records formatter,
CI, editor and runtime configuration inputs separately. Local `.env` secrets are excluded.

| Input | SHA-256 |
| --- | --- |
| `pyproject.toml` | `e553f7d09e9f62cd8a6fdecd00492e138ef75dc723eb01aed6793196824ebabe` |
| `requirements.txt` | `10fc9509811475c290a469a1e004b729cdefa4ca233014f4cb1458f3d620725e` |
| `requirements-dev.txt` | `78e2697eed46117b133a6748bd74d200f60c03c2f7b75d10b08dd12937011140` |
| `.github/workflows/tests.yml` | `5fbb8d734c8c34a378327db58527bef350bbcdb4f234e01cb646692dbb82ba00` |
| `.vscode/settings.json` | `02c9ce4e144f1caec058da4b2e5740af0610ee5cd30d25a1b4d4035e035866b7` |
| `.vscode/extensions.json` | `790ea189d5918b8ed7d2111821619f4ae6f21284d7679fe467bdaaa7c1f4b037` |
| `scripts/format_code.py` | `6f50a4411559ca471934e2979af7f321bb9cc9407f954847b7311f138e0c11ac` |
| `tests/unit/config/test_format_code.py` | `11652b5afdfb6b05961ac417c5006ab9fdb395ef32c6e71ea80008e23b80b6f3` |
| `.env.example` | `8a9811eee750390bac56eee79d7044a852fdeb4435d07bd8ea800e0257ec9b4b` |
| `.env.test` | `40b9e30608e524d56ab09d350a1024d5cba38ce643721eb60fe0460538d48802` |
| `Dockerfile` | `71eedddc4f3e2d4e492eae66b7f4c7ab88aff73cced3c7a56bb7aad2b8297924` |
| `docker-compose.smoke.yml` | `56a2c1792da56b587457b44813a86b26b222ed47e634b137b13bd9130f7e2f16` |
