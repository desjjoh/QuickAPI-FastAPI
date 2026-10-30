# Branch protections and hosted checks

[Documentation index](../README.md#documentation)

## Ruleset configuration

Branch rules are GitHub settings, separate from the checked-in workflow. Inspect the
[major-branch ruleset](https://github.com/desjjoh/QuickAPI-FastAPI/settings/rules/25976668)
before editing it. The intended protection policy is:

- Target `main`, `dev`, and `staging`.
- Restrict branch deletion and non-fast-forward pushes.
- Require pull requests; allow merge, squash, and rebase merge methods.
- Require zero approving reviews, without code-owner, last-push approval, stale-review
  dismissal, or conversation-resolution requirements.
- Allow repository administrators to bypass the rules. This policy does not prevent
  administrator bypass.
- Do not require branches to be up to date before merging.
- Require the verified Quality Deployment gate; retain the individual checks below
  until the hosted gate and ruleset transition have been verified.

A target rule can cover a branch that does not exist yet. Branch creation/deletion
and changes to the protection policy require separate repository administration.
Dated ruleset comparisons and hosted-run evidence are in [Verification](verification.md).

## Required status checks

The [Quality workflow](../.github/workflows/tests.yml) defines `Deployment gate`
as its aggregate check. It directly depends on all required jobs and accepts only
explicit success from each, including matrix job results. Its implementation and
offline tests do not establish hosted availability or ruleset enforcement.

Retain these individual contexts until the aggregate check is verified:

```text
dependency-security
static-analysis
test-layers (unit)
mysql-tests (integration)
mysql-tests (e2e)
combined-coverage
production-container
```

Remove obsolete required contexts `test-layers (integration)` and
`test-layers (e2e)` from existing rulesets. Those duplicate jobs are no longer
emitted; persistence layers are required through `mysql-tests (integration)` and
`mysql-tests (e2e)`. Retaining removed contexts would leave merges waiting forever.
The full coverage job also runs against MySQL.


The MySQL contexts above are defined by the workflow. Run it on GitHub and confirm
the actual check names before adding the new contexts; local runs do not establish
that they are available or enforced remotely.

The workflow runs on pull requests, pushes to `main`/`staging`/`dev`, merge groups,
manual dispatch and reusable workflow calls. It uses read-only contents permissions and cancels superseded
runs. A workflow definition or a pass at another commit does not establish that the
candidate commit passed; inspect its actual check results.

## Required-check configuration

1. Open [the existing ruleset settings](https://github.com/desjjoh/QuickAPI-FastAPI/settings/rules/25976668).
2. Verify the candidate's `Deployment gate` on GitHub and confirm its exact check
   context/source. Until then, preserve all individual requirements above.
3. Under **Require status checks to pass**, require the verified `Deployment gate`
   and select **GitHub Actions** as its source when offered. Remove superseded
   individual requirements only after verifying the aggregate. Preserve the intended branch,
   pull-request, merge, up-to-date, and bypass settings.
4. Save and reopen the rule to verify the configured list.
5. Verify that an ordinary pull request requires the gate for its candidate commit
   and that failed prerequisites prevent merging. A cancelled, pending or missing
   gate must not authorize a merge.

Check names belong to this repository. Select the check emitted by FastAPI's
workflow; sibling applications do not supply this repository's check evidence.

## Enforcement boundary

Until the transition is verified, require all listed individual checks. The production-container job depends on earlier jobs, and an earlier failure
can leave dependent jobs skipped. Requiring only the final dependent job does not
provide a fail-closed aggregate gate. An aggregate check must run and be verified
before it can replace this list; that requirement is tracked in [Milestones](milestones.md).
Local tests and Compose startup do not verify remote branch enforcement.
