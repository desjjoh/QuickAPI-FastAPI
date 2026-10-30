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

## Local checks and rollback boundary

Focused Windows checks use synthetic OCI archives and fake tool runners:

```powershell
python -m pytest -q tests/unit/config/test_release.py --no-cov
```

They cover wrong/missing attestations, tampering, source restrictions, failed gates,
stale evidence, version drift and publication identity. Actual container builds,
MySQL image qualification, scans and registry round-trips run in CI. Offline tests
do not establish hosted release success.

Image publication does not establish that an older image supports a newer database
schema. Retained-image selection, schema compatibility and the disposable rollback
exercise remain a separate scope in [Milestones](milestones.md).
