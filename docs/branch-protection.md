# Branch protections and hosted checks

[Documentation index](../README.md#documentation)

## Verified settings

Read from GitHub on 2026-10-27. Source rulesets are [FastAPI](https://github.com/desjjoh/QuickAPI-FastAPI/rules/25976668), [Express](https://github.com/desjjoh/QuickAPI-Express/rules/25689316), and NestJS [main](https://github.com/desjjoh/QuickAPI-NestJS/rules/16198248), [dev](https://github.com/desjjoh/QuickAPI-NestJS/rules/16198404), and [staging](https://github.com/desjjoh/QuickAPI-NestJS/rules/16198302). Recheck live settings before editing.

FastAPI's active `Protect major branches` ruleset already matches Express on:

- Targets: `main`, `dev`, and `staging`.
- Deletion and non-fast-forward restrictions.
- Pull requests required, zero required approving reviews, no stale-review dismissal, no code-owner/last-push approval requirement, and no required conversation resolution.
- Merge, squash, and rebase merge methods allowed.
- Repository administrators have an always-bypass entry, matching the reference; these rules are not a guarantee against administrator bypass.
- Required checks need not be up to date with the target branch (the strict setting is false).

The difference: Express requires its `Deployment gate` from GitHub Actions; FastAPI has a required-status-check rule with an **empty list**, so no checks are currently required by it. NestJS requires its own `Check` and `Migration Check`; its main/staging rules require up-to-date checks while dev does not. Those job names/policies are not interchangeable with FastAPI's current workflow.

Observed FastAPI branches were `main`, `dev`, and the active milestone branch. `staging` was not present, but its ruleset target is already configured for a future branch. This phase does not create or reset branches.

## Actual hosted check names

The successful [Quality run 39889071406](https://github.com/desjjoh/QuickAPI-FastAPI/actions/runs/39889071406), started on 2026-10-23 for commit `cfa6bdf27f5cdb4a7190ab17d948f4636ee8bbd5`, emitted all six checks below. Their names still match the current workflow:

```text
static-analysis
test-layers (unit)
test-layers (integration)
test-layers (e2e)
combined-coverage
production-container
```

These are real completed checks, not names inferred only from YAML. They do not prove that the newer dependency, timeout, or Compose changes passed hosted CI. Earlier uncertainty about selectable status checks should not be interpreted as evidence that the repository had never run CI.

The working-tree workflow now covers all pull requests, pushes to `main`/`staging`/`dev`, merge groups, and manual dispatch, with read-only contents permissions and concurrency cancellation for superseded runs. Existing job/check names remain unchanged. The trigger update itself still needs a hosted run after these changes are pushed through the normal PR workflow.

## Remaining manual setting

The connected GitHub tool exposes ruleset reads, not administrative writes. Native Firefox automation was previously blocked by browser URL-policy support. No ruleset changes were made in this phase.

To finish interim enforcement:

1. Open [FastAPI's existing ruleset settings](https://github.com/desjjoh/QuickAPI-FastAPI/settings/rules/25976668).
2. Under **Require status checks to pass**, add all six exact checks above. Select **GitHub Actions** as their source when offered; preserve the existing branch targets, PR settings, strict setting, and bypass policy.
3. Save, reopen the rule, and verify the six contexts are present. Verify an ordinary PR requires their results. Do not substitute Express's `Deployment gate`, NestJS's checks, or a future aggregate check.

Until phase 6D supplies an always-running fail-closed aggregate, requiring only the last dependent job is insufficient: earlier failures can skip dependent jobs. Phase 6E will switch/verify the required aggregate after it actually runs. Keep 1B's settings task pending until the interim list is saved and verified; local Compose success does not complete remote branch enforcement.
