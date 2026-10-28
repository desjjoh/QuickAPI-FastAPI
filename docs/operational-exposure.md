# Operational endpoint exposure

[Documentation index](../README.md#documentation)

## Defaults and overrides

The policy follows QuickAPI-Express: documentation, diagnostics, and metrics are
independently enabled by optional booleans. Omitted values default to `true` in
`development`/`test` and `false` in `production`.

| Setting | Controlled route families |
| --- | --- |
| `DOCS_ENABLED` | `/docs`, `/redoc`, `/openapi.json`, including Swagger OAuth redirect and nested documentation paths |
| `DIAGNOSTICS_ENABLED` | `/info`, `/system` |
| `METRICS_ENABLED` | `/metrics` |

Only literal `true`/`false` env values are accepted. Blank, numeric, mixed-case, and
other ambiguous values fail startup. Each flag independently overrides the environment
default. Precedence remains process environment > `.env` > code defaults; restart to
apply changes. The comments in `.env.example` show **production** defaults, so leaving
those assignments commented enables the endpoints when running in development/test.
For example, a private production scraper can explicitly enable only metrics:

```dotenv
METRICS_ENABLED=true
```

Native Python with the example's `ENV=development` enables all three by default.
Compose deliberately overrides `ENV=production`, so its API disables all three unless
explicit overrides are supplied. Local `DOCS_ENABLED=true` can enable container docs;
do not mistake that local override for a production access policy.

## Disabled behavior and schema

Disabled operational handlers are not registered. A guard also reserves each disabled
route family, returning the existing `{status,message,timestamp}` 404 envelope without
calling diagnostics, metadata collection, metric exposition, or schema generation.
The guard covers methods, case variants, trailing slashes, nested paths/assets, and
Swagger OAuth redirect without redirecting to a live alternative. Prefix matching has
path boundaries: `/information` is not part of `/info`. Mounted app prefixes are handled.
Each application builds its own router, preventing exposure leakage between instances.

Existing HTTP validation runs before this guard: for example, untrusted forwarding
headers can produce 400 and a valid browser preflight can return its CORS response.
Neither exposes the disabled handler. Trusted or untrusted forwarding cannot change
exposure flags. No bypass is granted based on client identity or a supplied API key.

When documentation is enabled, FastAPI retains its native `/openapi.json` path rather
than Express's `/docs-json`. Published OpenAPI describes registered routes only, so
independently disabled diagnostics/metrics are absent from the schema. With docs off,
neither UI, schema endpoint, nor OAuth redirect is installed. Disabled docs paths
receive normal security headers instead of the enabled documentation UI exemption.
The root greeting and favicon remain independent, matching the reference policy.

## Public probes and readiness compatibility change

`/health` and `/ready` remain independent of these flags and available to probes,
subject to the existing HTTP/rate policies. `/health` checks process liveness without
querying dependencies. `/ready` still evaluates startup state and required dependency
health, returning 200 when ready and 503 otherwise. Its public response is now minimal
in every environment, even when diagnostics are explicitly enabled:

```json
{"ready":true,"status":"ready","timestamp":"2026-10-27T12:00:00Z"}
```

**Compatibility change:** the public `checks` array and its dependency names/statuses/
timings are removed. Consumers should use HTTP status or `ready`/`status` for admission,
and must stop reading `ready.checks`. Internal service checks remain intact. `/system`
retains its existing diagnostic summary when explicitly enabled. The public OpenAPI
readiness schema matches the minimal response and no longer contains `ReadyCheck`.

## Metrics and access boundaries

`METRICS_ENABLED` controls HTTP exposition only. Request-outcome collection continues
when scraping is disabled; the five existing operational polling exclusions and the
[metric schema](deployment.md#metrics-and-request-outcomes) remain unchanged.

Enabling an endpoint makes it available **without application authentication**. CORS
and these flags do not authenticate callers; `METRICS_API_KEY` is not a consumed setting
and cannot protect scraping. Restrict enabled diagnostics/metrics using the consuming
service's trusted proxy/private-network/authentication boundary and verify direct-port
denial in the real hosting environment. That deployed boundary is separate from local
repository tests. No authentication subsystem or API-key scheme is introduced here.
