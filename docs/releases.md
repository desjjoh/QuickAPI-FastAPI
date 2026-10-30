# Verified container releases

[Documentation index](../README.md#documentation)

The [Release image workflow](../.github/workflows/release-image.yml) follows the
Express release lifecycle: require exact-source CI, build one unpublished OCI
candidate, qualify it, exercise publication in a disposable registry, then publish
the original archive. It publishes container images; hosting and deployment are
separate responsibilities.

## Source and version

Automatic releases follow successful **push** runs of `Quality` on `main` in this
repository. Pull-request and fork runs cannot authorize publication. The selected
commit must belong to main, and its latest push CI run/attempt must be completed,
successful and contain exactly one successful `Deployment gate`. The workflow
checks this through GitHub's API before building and again before registry login.

[VERSION](../VERSION) defines the release version and must match `APP_VERSION` in
[.env.example](../.env.example). Change both when preparing a new version and keep
local `.env` settings/comments synchronized as usual. Application `APP_VERSION`
remains runtime configuration; release qualification supplies the tracked version
to its API and migration containers through the tooling-only `SMOKE_APP_VERSION`.
The image's source, revision and version labels must match the selected source.

## Candidate and evidence

Buildx produces one linux/amd64 OCI archive with SPDX SBOM and maximum-detail
SLSA provenance. The containerd image store allows qualification of that candidate
without rebuilding. Publication retains the complete OCI index and its attached
attestation manifests.

The gate validates:

- OCI descriptor sizes and SHA-256 blob digests, including runtime layers.
- One runtime platform, exact source/version labels and unambiguous attestations.
- Attestation manifest/statement bindings, provenance repository/commit and an
  SPDX inventory containing every declared runtime Python package/version.
- The same loaded candidate's non-root identity, permissions, dependencies,
  migrations, MySQL CRUD/probes, API replacement, persistence, replay and shutdown.
- A fresh Trivy scan of the candidate's OCI layout with OS and Python inventories,
  using the shared [critical-only security policy](security.md).
- Hash-bound source, smoke result/log, raw scan, decision, SBOM and provenance.

Legacy BuildKit attestation manifests and OCI artifact subject binding are
supported. An empty statement subject relies on the enclosing manifest's verified
runtime binding; any supplied subject must identify that runtime. Unsupported or
ambiguous metadata fails qualification. These are validated build attestations,
not a claim of independent signing or a particular SLSA certification level.

Verification re-evaluates the current exception policy and checks evidence hashes
before publication. Failed attempts, modified files/archives, changed policy,
expired exceptions, scans older than 24 hours and invalid image identities block
publication. The allowed clock tolerance is five minutes into the future.

Temporary OCI layouts, registry data and login files are outside artifact uploads.
Reports, extracted attestations, identity records and failure diagnostics are
retained for 90 days. The original archive is not uploaded as a workflow artifact;
after publication, the registry retains the image and attached attestations.

## Registry rehearsal and publication

Every release, including a dry-run, exercises the publication implementation
against a fresh loopback-only temporary registry. It imports the archive, creates
commit/version tags, checks both digests, downloads the complete OCI layout and
validates the runtime and attestations again. Registry containers and temporary
storage are removed on success or failure.

Registry-exported OCI layouts may catalog additional referrers or aliases. The
round-trip check selects the independently approved candidate digest, rejects a
missing digest or conflicting descriptors, and verifies its full runtime and
attestation graph. The original build archive still requires exactly one root
candidate. `roundtrip-index.json` retains the returned catalog for diagnostics.

A real registry login occurs only after qualification, rehearsal and the final
source/evidence recheck succeed. The publisher imports the original OCI archive;
there is no second build. It verifies tag digests and the downloaded OCI layout,
then records `publication.json` and `release-image.env` containing:

```text
QUICKAPI_IMAGE=ghcr.io/owner/repository@sha256:<verified-index-digest>
```

Tags use the full source SHA and tracked version, matching Express. Tags can move;
the canonical immutable reference is the image index digest. Failed publication
can leave registry content or partially updated tags, but does not produce an
approved deployment reference. Preserve evidence and use a fresh qualified attempt
to retry; never promote incomplete evidence or bypass the gate.

Defaults use `ghcr.io/<lowercase-owner>/<lowercase-repository>` with the workflow's
GitHub token. Repository variables `CONTAINER_REGISTRY` and `CONTAINER_REPOSITORY`
can select another destination; use `REGISTRY_USERNAME`/`REGISTRY_PASSWORD` secrets
when the destination needs them. The `release` GitHub environment can apply the
repository's approval and branch restrictions. GHCR package permissions must allow
this repository's workflow to publish.

Trivy, regctl and disposable registry tool images are pulled, resolved to immutable
IDs and used by those IDs. Publisher credentials are mounted read-only through a
self-contained Docker login configuration. Host credential helpers are unsupported.
No scanner/publisher receives the Docker socket. No new application environment
settings or production requirements are introduced.

## Running a dry-run

1. Make the workflow/tooling available on the repository's default branch and main.
2. Obtain successful main-branch push `Quality` CI for the full source commit SHA.
3. Open **Actions → Release image → Run workflow**, select **main**, paste that
   commit into `git-ref`, and leave **dry-run** enabled.
4. Inspect the retained source, candidate, smoke, security and registry-test records.
5. For real publication, use an authorized run with dry-run disabled, or the
   automatic successful main push flow. Confirm `publication.json` and the digest
   reference; a dry-run does not publish to GHCR.

Each run builds and qualifies its own candidate. A later publishing run does not
silently reuse a previous dry-run's approval. GitHub service availability and
registry permissions are prerequisites for hosted qualification.

## Local checks

Focused Windows checks use synthetic OCI archives and fake tool runners:

```powershell
python -m pytest -q tests/unit/config/test_release.py --no-cov
```

They cover wrong/missing attestations, tampering, source restrictions, failed gates,
stale evidence, version drift and publication identity. Actual container builds,
MySQL image qualification, scans and registry round-trips run in CI. Offline tests
do not establish hosted release success.

## Retained-image rollback

Rollback selects an earlier **published image digest**. It does not rebuild that
source, move registry tags, reverse migrations or reset a database. Preserve
successful `publication.json` records and their source, SBOM/provenance, scan and
smoke evidence beyond CI retention when your rollback horizon requires it. Retain
the corresponding registry digests against deletion/garbage collection.

The application requires exact Alembic revision equality. An older image can be
considered for application-only rollback only when it expects the current single
schema head and the release pair passes compatibility qualification. Head equality
is necessary, not sufficient: business/data contracts and retry semantics also
have to remain compatible. Changes requiring another schema revision need their
own recovery plan; do not bypass readiness or stamp/downgrade the database to make
an image start.

### Disposable qualification

The manual [Rollback qualification workflow](../.github/workflows/rollback-check.yml)
runs trusted main-branch tooling with registry read permission. Select both input
references from successful publication records: `current-image` is the image being
replaced and `rollback-image` is the earlier retained version. Use full
`repository@sha256:<index-digest>` references from this application's configured
registry/repository. Tags, identical references and same-source rebuilds are
rejected. Image source/version/user labels, pulled digests and both migration heads
are verified before any database is started.

1. In **Actions → Rollback qualification → Run workflow**, select **main**.
2. Paste the two retained image references into `current-image` and `rollback-image`.
3. Review `rollback-evidence-<run>-<attempt>`, including `result.json`, image/head
   identities, transition records, command diagnostics and API/MySQL logs.

The check owns `quickapi-fastapi-rollback`, publishes no API/database host ports and
uses temporary MySQL storage. It migrates a fresh database **once** with the current
image, then exercises current → rollback → current against that same running MySQL
container. A read-only live schema check precedes every API start. Each transition
replaces only the API and verifies its requested immutable image reference.

The current image creates/updates retained state and a keyed response. The rollback
image must read it, replay the original exact response without another mutation,
and update/create resources. Returning to the current image must preserve those
writes, replay the original response and accept further updates/deletion. All three
API instances must stop cleanly. Failure or cleanup failure leaves `passed: false`;
temporary project resources are removed and reports are retained for 90 days.

The command can also be invoked explicitly after installing development tooling
and preparing guarded `.env.test` configuration:

```powershell
python -m scripts.test_rollback --current-image 'ghcr.io/owner/repository@sha256:<current-digest>' --rollback-image 'ghcr.io/owner/repository@sha256:<retained-digest>' --source 'https://github.com/owner/repository'
```

Use registry login when image pulls require it. The workflow reuses release
registry variables/secrets. These are tooling settings, not application `.env`
configuration. Local verification normally uses
`python -m pytest -q tests/unit/config/test_rollback.py --no-cov`; live Docker/MySQL
rollback qualification stays in CI.

### Applying a qualified rollback

Before a real application rollback, confirm the current database head, the
reviewed release pair's data compatibility and current security acceptance. A
compatibility test does not refresh an earlier vulnerability scan or independently
verify an operator's claim that a reference came from a successful release.
The current image is checked against current build-content rules. A retained
image is checked for its non-root runtime identity and application compatibility;
historical tool inventory, such as an older curl installation, does not by itself
invalidate that compatibility evidence. Security acceptance remains a separate review.

Withdraw traffic/admission and drain/stop the current API. Select the retained
verified digest in the deployment configuration, without running migrations, then
start it and verify readiness, representative reads/writes, retry behavior and
logs before restoring traffic. Keep the replaced digest and deployment record.
If the retained image fails compatibility/readiness, leave traffic withdrawn and
use the recorded current digest or a reviewed forward repair. Database restoration
and destructive schema reversal require separate qualification.

This repository exercises the image/database procedure in disposable infrastructure.
Hosting-specific traffic withdrawal, rollout and restore remain deferred. A first
published release has no historical image pair; an actual retained-image run is
required once a second compatible release exists.
