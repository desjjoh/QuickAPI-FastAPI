# Technical backlog

[Documentation index](../README.md#documentation)

Keep only unresolved follow-ups and explicitly deferred capabilities here. Remove
an item when its completion is established; routine maintenance and supported
behavior belong in the relevant core guide.

## Retained-image rollback qualification

Confirm a successful historical current → rollback → current run using two
compatible, distinct published releases. The workflow and rollback tooling already
exist. Check existing qualification records first; close this item if an applicable
successful run is available. Exact schema-head equality is necessary but does not
replace business/data/replay compatibility or current security acceptance.

## Hosted deployment qualification

Deferred until hosting is selected:

- Verify real proxy/client-IP trust, browser CORS, restricted diagnostics/metrics,
  and direct listener denial.
- Configure and exercise server/ingress header-receive and whole-upload deadlines
  using slow headers and stalled/trickled uploads. Application response timers
  and keep-alive settings do not establish these protections.
- Exercise traffic withdrawal, supervisor termination grace, database outages,
  and recovery in the deployed topology.
- Verify database CA/DNS identity, certificate rotation, fleet pool sizing,
  durable storage, encrypted backups, and restoration.
- Establish log access/retention, dashboard integration, and operational ownership.

Disposable CI and local Docker do not qualify these deployment-owned conditions.
Keep procedures in [Deployment](deployment.md) and record execution with the release,
not as a permanent documentation diary.

## Shared rate limiting

Retain process-local limiting until deployment-wide enforcement is required.
Before adding shared Redis enforcement, define outage behavior, bounded storage,
expiry, and configuration; preserve rolling windows and test multiple instances.
There is no Redis implementation or configuration in the current application.
