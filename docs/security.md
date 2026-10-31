# Security

[Documentation index](../README.md#documentation)

## Application access

The item API has no authentication, account system, or authorization middleware.
Every reachable client can use its operations subject to validation, rate limits,
revision checks, and replay policy. CORS, versions, keys, and unused credential
settings do not grant or restrict permissions. Keep the deployment within its
intended trust boundary.

## Operational access

Documentation, diagnostics, and metrics default on in development/test and off
in production. Availability flags do not authenticate callers. Disabled surfaces
return 404 and are excluded from the exposed schema. Named endpoint spellings,
documentation assets, and HEAD follow the same exposure controls. `/health` and
`/ready` remain public; readiness omits dependency identities and probe timings.
Restrict enabled diagnostics/metrics at ingress/private networks, block direct
listener bypass, and enable documentation only for its intended audience.
See [Configuration](configuration.md#operational-surfaces).

## Proxy and browser boundaries

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

CORS uses exact configured browser origins and credential policy. It is browser
response-access control, not authentication. Requests rejected before CORS do not
gain browser permission. Custom allowed headers must include `idempotency-key`
for keyed browser mutations. `Set-Cookie` is never readable by browser JavaScript,
even when exposed. Configure public HTTPS and server/ingress transport protection;
application response timers do not time incomplete headers.

## Rate limiting

### Admission, bounded storage, and recovery

Each application instance owns a process-local store. Client identities are resolved
by [trusted-proxy policy](configuration.md#browser-and-http-settings) before admission;
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

### HTTP responses

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

### Endpoint and middleware policy

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

### Process and deployment boundary

Stores are independent across app instances, workers, replicas, and restarts. This is
not a shared global quota. A deployment requiring shared quotas needs a shared
enforcement store. Correct trusted-proxy configuration matters: an untrusted
forwarding header cannot allocate a distinct identity, and clients sharing an actual
resolved address share quota. Capacity and quota tests do not establish a distributed
limit or deployed-ingress guarantee.

## Sensitive data and diagnostics

Structured fields have an explicit allowlist. Request/response objects, bodies,
queries, route parameters, raw headers/cookies, credentials/tokens, replay payloads,
SQL, arbitrary nested metadata, and raw tracebacks are not serialized. Public API
error envelopes/messages follow [API contracts](architecture.md#api-contracts); internal rejection
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

## Dependency and image security

The gates follow Express: unexcepted **CRITICAL** production dependency or image
findings block approval, including findings without fixes. HIGH and MEDIUM findings
produce workflow warnings. LOW and UNKNOWN findings remain in the reports.
Development-only dependency findings are visible and nonblocking regardless of
severity. Missing evidence, scanner failures and invalid exceptions always block.

### Dependency audit

`python -m scripts.security_scan dependencies` scans runtime and full
runtime/development requirements separately with Trivy. Requirements must use
exact `==` pins; the development file includes the runtime file through
`-r requirements.txt`. Other directives, unpinned entries and overlapping package
declarations fail validation. Generated scan inputs contain the complete manually
pinned inventories. Every declared package/version must appear in the report.

Trivy's [Python support](https://trivy.dev/docs/latest/guide/coverage/language/python/)
supplies severity data for Python requirements; pip-audit alone does not
provide the severity classification needed by this policy. This does not change
pip installation or add scanner dependencies to the application requirements.
Only findings belonging exclusively to development requirements are marked
development-only. A runtime package appearing in the full report remains runtime.

### Runtime image scan

CI resolves the built image's immutable Docker image ID, passes that ID to
MySQL qualification, then scans that same ID with
`python -m scripts.security_scan image --image sha256:<image-config-digest>`.
Mutable image tags are rejected by the image scanner.

The gate exports the image to a temporary archive and verifies that the archive
configuration hashes to the selected image ID. Trivy reads that archive through a
read-only mount without a Docker socket. The archive hash must remain unchanged,
and the report must identify the selected image and contain nonempty OS and
Python package inventories, including every declared runtime package/version.
Unsupported/end-of-life OS evidence fails the gate. Temporary archives are
removed on success or failure.

### Scanner identity and retained evidence

The tooling defaults to `aquasec/trivy:latest`, matching Express. Each invocation
pulls the reference and resolves its immutable ID before running it. The selected
reference, actual scanner ID/version and image/archive identity are recorded.
`TRIVY_SCANNER_IMAGE` can select another scanner reference for CI tooling; it is
not an application setting and does not belong in `.env`.

Scanner defaults update the vulnerability database; the gate does not enable
offline, ignore-unfixed, severity-filter or database-update-skipping options.
Security scans require Docker and registry/database network access. The local
verification policy uses offline Windows fixture tests; actual scans run in CI.
The scanner's root-owned cache lives under ignored `.cache/trivy/`, outside all
artifact upload paths. Uploads select reports and logs, never scanner caches.

Debian inventory versions are reconstructed from upstream version, release and
epoch before matching vulnerability records. Matching remains exact; another
release or epoch cannot satisfy a finding's installed-version requirement.

Ignored `test-artifacts/security/dependencies/` and `image/` retain raw reports,
`result.json`, `identity.json`, command diagnostics and `summary.md`. CI uploads
these and the applicable exception register with `if: always()` and 14-day
retention, including failures. Findings can appear in both runtime and full
dependency reports; warning counts are per report, not unique vulnerabilities.
Reports are time-specific advisory evidence, not proof of exploitability.

The jobs fail on prohibited findings or unusable evidence. The always-running
Deployment gate requires dependency security and production-container success;
saved branch protection must be verified independently; see [Testing](testing.md#branch-protection).
[Release candidates](deployment.md#releases-and-rollback) receive their own bound scan and policy
re-evaluation before publication; a passing PR scan does not approve an image
rebuilt later. Candidate publication does not rebuild the qualified artifact.

### Remediation

Update the affected manually pinned requirement and any framework dependency
needed to support its fix. Qualify the existing API/transaction contract after a
FastAPI/Starlette update; do not weaken response or replay validation to make an
upgrade pass. Image installer updates use the Dockerfile's `PIP_VERSION`.

Fresh image builds apply available stable Trixie updates and omit curl by using
Python readiness probes. A pinned base may already contain the latest supported
runtime, while distribution advisories still list unfixed packages. Retain those
findings and review upstream patches; do not remove warnings or invent exceptions
to reduce the count. Only a fresh scan of the rebuilt image establishes the
updated findings. Critical-only blocking and exact exception rules apply to every candidate.

### Exceptions

Separate registers start empty:

- [Dependency exceptions](../security/dependency-audit-exceptions.json)
- [Image exceptions](../security/container-vulnerability-exceptions.json)

Each reviewed exception must contain exactly these fields:

```json
{
  "vulnerabilityId": "CVE-YYYY-NNNN",
  "packageName": "exact-package-name",
  "installedVersion": "1.2.3",
  "packagePath": null,
  "target": "exact report target",
  "type": "exact report type",
  "owner": "responsible maintainer",
  "reason": "Impact assessment, mitigation and remediation plan",
  "review": "review or issue reference",
  "expiresOn": "YYYY-MM-DD"
}
```

The outer register is `{"version": 1, "exceptions": [...]}`. All six scope fields
must match exactly, including the package path (`null` only when absent). No
wildcards are allowed. Dates expire at 00:00 UTC and must be in the future within
30 days of evaluation. Malformed, expired, overlong or duplicate entries fail even
when no finding matches. Exceptions leave findings visible and never authorize
scanner failures or missing evidence. Updates and remediation are preferable;
adding an exception is a reviewed risk-acceptance decision.
