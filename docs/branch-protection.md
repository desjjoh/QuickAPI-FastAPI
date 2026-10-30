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
- Require `Deployment gate` from GitHub Actions as the sole required status check.

A target rule can cover a branch that does not exist yet. Branch creation/deletion
and changes to the protection policy require separate repository administration.
Dated ruleset comparisons and hosted-run evidence are in [Verification](verification.md).

## Required status checks

The [Quality workflow](../.github/workflows/tests.yml) emits the required check:

```text
Deployment gate
```

Its source is GitHub Actions (integration ID `15368`). The aggregate directly
requires dependency security, static analysis, unit tests, MySQL integration/E2E,
combined coverage and production-container qualification/security. Only explicit
success from every prerequisite passes. Failed, cancelled, skipped, missing or
malformed results block approval. Individual job checks still run and appear in
the PR; the ruleset requires their aggregate rather than listing them separately.

The workflow runs on pull requests, pushes to `main`/`staging`/`dev`, merge groups,
manual dispatch and reusable workflow calls. It uses read-only contents permissions and cancels superseded
runs. A workflow definition or a pass at another commit does not establish that the
candidate commit passed; inspect its actual check results.

## Required-check configuration

1. Open [the existing ruleset settings](https://github.com/desjjoh/QuickAPI-FastAPI/settings/rules/25976668).
2. Confirm the candidate's `Deployment gate` on GitHub and its GitHub Actions source.
3. Under **Require status checks to pass**, require only `Deployment gate`
   and select **GitHub Actions** as its source. Preserve the intended branch,
   pull-request, merge, up-to-date, and bypass settings.
4. Save and reopen the rule to verify the configured list.
5. Verify that an ordinary pull request requires the gate for its candidate commit
   and that failed prerequisites prevent merging. A cancelled, pending or missing
   gate must not authorize a merge.

Check names belong to this repository. Select the check emitted by FastAPI's
workflow; sibling applications do not supply this repository's check evidence.

## Enforcement boundary

The gate runs with `if: always()` so prerequisite failures cannot become an
approved skipped aggregate. Cancelling the workflow can cancel the gate; an absent,
pending or cancelled gate is not approval. Requiring production-container alone
would not provide this aggregate guarantee. Administrator bypass remains enabled
by policy. Local tests and Compose startup do not verify remote branch enforcement;
dated hosted execution and saved ruleset evidence are recorded in
[Verification](verification.md).
