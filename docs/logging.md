# Logging and diagnostics

[Documentation index](../README.md#documentation)

## Output and levels

`ENV` selects presentation: development/test use single-line console output;
production uses JSON records with UTC ISO timestamps. `LOG_LEVEL` accepts `DEBUG`,
`INFO`, `WARN`, or `ERROR`, defaults to `INFO`, and filters both application output
and the standard logging bridge. There is no separate output-format setting.

| Event | Python level |
| --- | --- |
| Successful request access record | DEBUG |
| Normal application lifecycle | INFO |
| Expected client rejection / aborted request | WARNING |
| Server error / unexpected failure | ERROR |
| Fatal initialization/runtime failure | CRITICAL |

At INFO, successful request logs are hidden while lifecycle messages are visible.
Metrics and request-outcome observation are independent of log filtering. There is
one access record per settled response outcome; a rejection/failure can also have a
separate fixed diagnostic event. An aborted response whose headers carry a server
error status uses ERROR.

Console layout is `timestamp [pid] [level] [request-id] message`, with the request ID
when available. Console timestamps use local time. Control characters in messages
and context fields are escaped to keep a single record per line. Production output
has no ANSI styling and uses ASCII-compatible JSON escaping, including for Unicode
values; JSON consumers recover the original string values normally.

## Structured records

Production records use `time`, `pid`, `hostname`, `levelLabel`, and `msg`. Supported
context/outcome fields are `requestId`, `method`, `ip`, `route`, `status`, `durationMs`,
`outcome`, and `headersSent`. Status is absent when response headers have not been
accepted. Duration uses milliseconds. Methods and declared route templates follow
[the outcome contract](deployment.md#metrics-and-request-outcomes).

Request correlation is preserved for concurrent requests and final server errors
after request-context cleanup. Raw paths are not bound to logging context. Generic
logger callers must use fixed, safe messages and declared route templates; allowed
metadata fields are not a place to embed request/provider data.

## Privacy and error diagnostics

Structured fields have an explicit allowlist. Request/response objects, bodies,
queries, route parameters, raw headers/cookies, credentials/tokens, replay payloads,
SQL, arbitrary nested metadata, and raw tracebacks are not serialized. Public API
error envelopes/messages follow [API contracts](api-contracts.md); internal rejection
logs use `HTTP request rejected.` and unexpected failures use `HTTP request failed.`
without copying public details or exception text into the log message.

The `error`, `err`, `reason`, and `exception` aliases use the diagnostic serializer;
`exception` is emitted as `error`. Diagnostics include only:

- `errorType`: an allowlisted Python/SQLAlchemy category, otherwise `UnknownError`.
- `errorCode`: an allowlisted native numeric error-code mapping when available.
- `errorFingerprint`: SHA-256 of up to 64 traceback frame identities when available.

Exception messages, argument values, SQL parameters, source lines, local variables,
raw frame paths, and cause payloads are not emitted. A fingerprint is correlation
metadata, not an actionable stack trace. Unexpected/hostile diagnostic objects fall
back to `UnknownError`. SQLAlchemy uses `echo=False` and `hide_parameters=True`.

## Server, dependency, and bootstrap output

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

## Verification

[Logging unit tests](../tests/unit/config/test_logging_privacy.py) cover output modes,
levels, metadata filtering, diagnostics, control characters, non-finite metadata,
hostile errors, and ASCII-only streams. [Integration checks](../tests/integration/middleware/test_logging_privacy.py)
cover fresh-process configuration/fatal/dependency output and real h11/httptools
server failures with safe, correlated JSON. Request outcome and deadline tests cover
concurrency, aborts, delayed cleanup, and late failures. Recorded execution evidence
is in [Verification](verification.md).
