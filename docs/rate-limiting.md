# Bounded rate limiting

[Documentation index](../README.md#documentation)

## Configuration

The limiter enforces a bounded exact rolling window. Optional
overrides in `.env.example` show code defaults; normal precedence remains process
environment > `.env` > defaults. Restart to apply changes.

| Setting                  | Default | Accepted integer range |
| ------------------------ | ------- | ---------------------- |
| `RATE_LIMIT_WINDOW_MS`   | 60000   | 1-86400000             |
| `RATE_LIMIT_MAX`         | 200     | 1-10000                |
| `RATE_LIMIT_MAX_CLIENTS` | 10000   | 1-100000               |

`RATE_LIMIT_MAX * RATE_LIMIT_MAX_CLIENTS` must not exceed **2000000 timestamp slots**.
Missing values use defaults; blank/fractional/non-finite/boolean/out-of-range values
fail startup. The same shared policy validates direct limiter construction. Raising
the request quota may require lowering client capacity to retain the combined bound.
For example, 1000 requests with 2000 tracked clients reaches the same slot ceiling.

The default quota is **200 admitted requests in the preceding 60 seconds per client**.
There is no separate burst budget or fixed-window reset. Python callers use
`admit(identity)` to obtain an explicit admission/rejection decision. HTTP errors use
the `{status,message,timestamp}` envelope.

## Admission, bounded storage, and recovery

Each application instance owns a process-local store. Client identities are resolved
by [trusted-proxy policy](http-policy.md#client-identity-and-proxy-trust) before admission;
the limiter never reads forwarding headers itself. Missing peer identity shares one
`unknown` bucket. SHA-256 digest keys have a fixed stored size; raw identity strings
are not retained as store keys.

Each tracked client owns a fixed-size `array('d')` timestamp ring allocated only when
a new identity is admitted. Its capacity is `RATE_LIMIT_MAX`; timestamps use monotonic
milliseconds. At the configured ceiling, timestamp buffers occupy 16000000 bytes,
plus separately bounded client, key, array, and mapping overhead. This is a storage
bound, not a promise of total process RSS. A lock makes admission/usage snapshots
atomic for event-loop and concurrent thread callers.

On admission, timestamps at or before `now - window` expire. An accepted request adds
one timestamp and updates the client's last-admission expiry. Clients are ordered by
that expiry; expired clients are reclaimed during subsequent admission. No background
GC task is needed. Rejections add no history, do not extend expiry, and do not move a
client in expiry order. An idle process can retain expired data until the next admission,
but its storage remains bounded.

When the client table is full, existing clients may still use remaining quota. A new
identity is rejected rather than evicting an active client and resetting its quota.
Capacity becomes available when an entire tracked client's window expires. The public
Python `usage` snapshot reports tracked clients, stored timestamps, and allocated
slots; it creates no additional HTTP endpoint.

## HTTP responses

| Decision                                | HTTP behavior                                                              |
| --------------------------------------- | -------------------------------------------------------------------------- |
| Admitted                                | Request proceeds; wrapped responses include `X-RateLimit-Result: accepted` |
| Existing client quota exhausted         | 429, `X-RateLimit-Result: rejected`, positive integer `Retry-After`        |
| New identity at client-storage capacity | 503 with the same rejection/retry headers                                  |

429 uses `Too many requests — limit is N per Ws.`. 503 uses `Rate limiter capacity is exhausted.
Try again later.` Both retain the existing error envelope. `Retry-After` is the
remaining delay rounded up to whole seconds, with a minimum of one: the next timestamp
expiry for 429, or next client expiry for 503. Capacity retry timing is advisory;
additional admissions by active clients can change future availability.

For example, with a 2500ms window and two slots, admissions at 0ms and 1000ms cause a
request at 1250ms to receive `Retry-After: 2`. At 2500ms the first timestamp expires
and a new request is admitted without resetting the entire history.

## Endpoint and middleware policy

Security headers wrap rate-limit responses. Admission runs before header sanitization,
application header budgets, timeout, content/method policy, CORS, body limits, exposure
guards and routing. Unknown allowed-to-drop headers are removed before header-size
accounting. Retained over-budget headers return 431 after consuming admitted quota;
dropped unknown headers do not trigger that application size rejection. Trusted-proxy
interpretation retains its separate early raw-header bounds.

`/health`, `/ready`, `/info`, `/system`, `/metrics`, docs/schema, unknown routes, and
browser preflights share the client's quota. A probe can therefore receive 429/503
from the limiter instead of its normal liveness/readiness response. Plan probe identity,
frequency, and capacity accordingly; there is no special header or trusted-client bypass.
Exact native `/favicon.ico` GET/HEAD requests are exempt and both methods serve the icon;
other favicon methods/paths are ordinary admitted requests. See the
[metrics contract](deployment.md#metrics-and-request-outcomes) for telemetry exclusions.

Limiter 429/503 responses occur before CORS and do not carry its
allow-origin headers. Cross-origin browser JavaScript can therefore observe a CORS
failure rather than read the JSON/retry header. This ordering applies to both quota
and client-capacity rejection.

## Process and deployment boundary

Stores are independent across app instances, workers, replicas, and restarts. This is
not a shared global quota. A deployment requiring shared quotas needs a shared
enforcement store. Correct trusted-proxy configuration matters: an untrusted
forwarding header cannot allocate a distinct identity, and clients sharing an actual
resolved address share quota. Capacity and quota tests do not establish a distributed
limit or deployed-ingress guarantee.
