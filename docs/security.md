# Dependency and image security

[Documentation index](../README.md#documentation)

The gates follow Express: unexcepted **CRITICAL** production dependency or image
findings block approval, including findings without fixes. HIGH and MEDIUM findings
produce workflow warnings. LOW and UNKNOWN findings remain in the reports.
Development-only dependency findings are visible and nonblocking regardless of
severity. Missing evidence, scanner failures and invalid exceptions always block.

## Dependency audit

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

## Runtime image scan

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

## Scanner identity and retained evidence

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
remote branch enforcement is tracked separately in [Milestones](milestones.md).
[Release candidates](releases.md) receive their own bound scan and policy
re-evaluation before publication; a passing PR scan does not approve an image
rebuilt later. Candidate publication does not rebuild the qualified artifact.

## Exceptions

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
