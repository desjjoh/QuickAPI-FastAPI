# HTTP configuration

[Documentation index](../README.md#documentation)

## Defaults and overrides

[Settings](../app/config/environment.py) owns defaults and startup validation.
Normal precedence is **process environment > `.env` > code defaults**. Settings are
loaded once at startup; restart after changing configuration. Constructor values
used by tests take precedence over those sources.

[`.env.example`](../.env.example) groups required identity/database values and optional
policy overrides. Commented assignments show actual defaults, not additional required
configuration. Copy it only when creating a new `.env`; reconcile an existing file
without discarding credentials or local overrides. Keep shared comments synchronized.
Lists use comma-separated values, not JSON; surrounding entry whitespace is trimmed
and duplicates are removed. Header names/media types normalize to lowercase; methods
must already be uppercase. Booleans accept exactly `true` or `false`.

Missing optional values use defaults. Empty values are rejected except `TRUST_PROXY`,
`CORS_ALLOWED_HEADERS`, and `CORS_EXPOSED_HEADERS`, where empty means an empty list.
The existing published-port settings separately accept empty values as defaults.

## Browser policy

| Setting | Default | Validation |
| --- | --- | --- |
| `CORS_ORIGINS` | `http://localhost:3000` | 1-100 exact serialized HTTP(S) origins; no wildcard, credentials, path/trailing slash, query, fragment, or explicit default port |
| `CORS_METHODS` | `GET,POST,PUT,DELETE,PATCH,HEAD,OPTIONS` | Non-empty subset of `HTTP_ALLOWED_METHODS` |
| `CORS_ALLOWED_HEADERS` | `content-type,authorization,x-requested-with` | Up to 100 supported names; forwarding/hop-by-hop names are reserved |
| `CORS_EXPOSED_HEADERS` | `authorization,set-cookie` | Same syntax/count rules; empty disables configured exposed headers |
| `CORS_CREDENTIALS` | `true` | Boolean |
| `CORS_MAX_AGE_SECONDS` | `86400` | Integer 0-86400; zero disables preflight caching |

For example, to use both local frontend conventions:

```dotenv
CORS_ORIGINS="http://localhost:3000,http://localhost:5173"
```

Production must configure its actual frontend origins when browser access is needed.
The localhost default is identical in all environments. Allowed origins receive origin-specific response headers and `Vary: Origin`.
Disallowed origins/method/header preflights receive the JSON 403 error envelope. Requests
without Origin remain valid and receive no CORS response headers. Configured request
headers also pass the application's sanitizer, which otherwise retains its existing
base allowlist and protocol restrictions. Listing `set-cookie` does not make that
header readable by browser JavaScript. CORS is browser policy, not authentication.

## Client identity and proxy trust

`TRUST_PROXY` defaults to an empty list. It accepts up to 100 IPv4/IPv6 addresses or
CIDRs with nonzero numeric prefixes, for example:

```dotenv
TRUST_PROXY="127.0.0.1,10.20.0.0/24,::1"
```

Configure only actual connecting proxies. Hostnames, hop counts, wildcards, scoped
IPv6 addresses, netmask notation, and blanket `/0` networks are rejected at startup.
Host bits in a CIDR normalize to its network.

The application checks the original connecting peer before interpreting
`X-Forwarded-For` or `X-Forwarded-Proto`. For a trusted peer, the rightmost untrusted
address in a validated IP chain becomes the client; an entirely trusted chain uses
its leftmost address. Proto must be exactly `http` or `https`. Consumed headers are
removed before sanitization. Untrusted, malformed, or duplicate forwarding headers
are not consumed and remain subject to existing header rejection; other forwarding
headers remain forbidden. Proxy resolution runs before request context so context,
logging, and limiting use the same effective client identity.

`python -m app.main` explicitly disables Uvicorn's automatic proxy handling so a
second policy cannot rewrite the peer first. External server commands must do the
same, for example:

```bash
uvicorn app.config.application:app --no-proxy-headers
```

The app cannot recover the original peer if an external server has already rewritten
it. A real deployed proxy must overwrite/append forwarding headers correctly and
prevent untrusted direct access according to the hosting design. Loopback socket
checks prove repository behavior, not the eventual ingress topology.

## Request budgets and application policy

| Setting | Default | Accepted integer range |
| --- | --- | --- |
| `REQUEST_TIMEOUT_MS` | 10000 | 1-2147483647 |
| `REQUEST_FIRST_BODY_TIMEOUT_MS` | 5000 | 1-2147483647 |
| `REQUEST_CHUNK_TIMEOUT_MS` | 2000 | 1-2147483647 |
| `HTTP_MAX_BODY_BYTES` | 1048576 (1 MiB) | 1-1073741824 |
| `HTTP_MAX_HEADER_COUNT` | 100 | 1-10000 |
| `HTTP_MAX_SINGLE_HEADER_BYTES` | 4096 | 1-1048576 |
| `HTTP_MAX_TOTAL_HEADER_BYTES` | 8192 | 1-16777216 |

Both body-wait deadlines must be no greater than the total response deadline.
The single-header byte budget must not exceed the total budget. Fractions, booleans,
blank values, non-finite values, and out-of-range numbers fail startup. Milliseconds
convert to seconds only when configuring the existing Python timeout middleware;
[response/stream/cancellation behavior](request-timeouts.md) is unchanged.

Header byte accounting remains name + value, excluding wire framing. Parsed-header
budgets run before CORS preflight short-circuiting and before sanitizer filtering,
so unknown headers cannot evade the limits by being dropped. Trusted proxy handling
consumes headers only after the original count/size budgets pass. This protects the
application policy boundary; a server may reject a request before ASGI with its own
limits, and these settings do not cap memory used while parsing wire headers.

`HTTP_ALLOWED_METHODS` defaults to `GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS` and accepts
only a non-empty subset of these methods. `HTTP_ALLOWED_CONTENT_TYPES` defaults to
`application/json,multipart/form-data`; it accepts 1-100 exact media types without
parameters or wildcards. Existing route validation and body-method rules remain:
allowing a media type does not change an item's JSON schema or make no-body methods
accept bodies. Chunked transfer and unsafe-header restrictions remain code policy.
[Rate limiting](rate-limiting.md) defines the three validated rolling-window settings,
combined storage bound, response timing, and probe/preflight policy.

## Server receive protection boundary

The application receives an ASGI scope after HTTP headers have been parsed.
`REQUEST_FIRST_BODY_TIMEOUT_MS` is a body-read deadline, not a slow-header deadline;
`REQUEST_TIMEOUT_MS` is a routed response deadline, not a TCP acceptance deadline.
Uvicorn keep-alive timing is also not a header-receive timeout. No ineffective
`HTTP_HEADERS_TIMEOUT_MS` or entire-wire-request setting is exposed.

True header/whole-upload receive protection requires a supported server or the
selected ingress. Configuration and real slow-client verification remain open in
the deployment backlog; application settings alone do not complete that guarantee.


## Operational availability

[Operational exposure](operational-exposure.md) is controlled by `DOCS_ENABLED`,
`DIAGNOSTICS_ENABLED`, and `METRICS_ENABLED`. These optional strict booleans default
on in development/test and off in production; commented env examples show production
values. They control availability, not authentication. Public probes remain minimal
and independent. All three use the same process/dotenv precedence described above.
