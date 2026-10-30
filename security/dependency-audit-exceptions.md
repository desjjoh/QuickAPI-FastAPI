# Dependency audit exceptions

[dependency-audit-exceptions.json](dependency-audit-exceptions.json) is the
machine-readable register. It starts empty. Unexcepted critical runtime findings
block; development-only findings remain visible and nonblocking.

Use the exact scope, review and expiry requirements in
[Security](../docs/security.md#exceptions). Every entry needs a responsible owner,
justification, review reference and UTC expiry within 30 days. An exception does
not suppress unrelated packages, versions, paths or advisories, and cannot bypass
scanner/evidence failures. Prefer compatible dependency updates to exceptions.
