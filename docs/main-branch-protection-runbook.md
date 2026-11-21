# Main branch protection — administrator runbook

**Tracking:** [Issue #933](https://github.com/kimtk94/Codex/issues/933)

## Status before activation

The live repository was checked on 2026-11-22 KST. The main branch was **unprotected**, and the repository had no rulesets. No automation is authorized to claim otherwise until a post-change API readback succeeds.

Evidence:
- [PR #932](https://github.com/kimtk94/Codex/pull/932) added read-only indirect Git write auditing.
- [PR #934](https://github.com/kimtk94/Codex/pull/934) added the always-on check **`main-write-guard`** for all pull requests targeting `main`, without pull-request path filters.
- A green `main-write-guard` certifies only static checks for **detectable** direct-main pushes, unknown push targets, and main-target writes in directly referenced non-test scripts. It is **not** a complete dependency, third-party action, or credentials audit.

## Apply in GitHub repository Settings (repository administrator)

1. Go to [repository rulesets](https://github.com/kimtk94/Codex/settings/rules), then **New ruleset → New branch ruleset**.
2. Give it a name such as `main-pr-only`. Target **branch `main` only**, and set enforcement **Active**.
3. Enable **Require a pull request before merging**. For the current single-maintainer workflow, use **0 required approvals** unless a reviewer is actually available.
4. Enable **Restrict deletions** and **Block force pushes**. Do **not** set a bypass for normal automation tokens or repository administrators.
5. Enable **Require status checks to pass before merging**, and select exactly the existing **`main-write-guard`** check from **GitHub Actions**. Only add another required check after confirming it is reported on **every** relevant PR; path-filtered checks can remain Pending forever.
6. Do **not** enable a merge queue without also adding `merge_group` triggers to required workflows. Leave optional stricter rules (signed commits, linear history, branch freshness, minimum approvals) unchanged until regression testing confirms compatibility.
7. Save the ruleset, then perform read-back verification. Do not rely only on Settings screenshots.

## Required post-activation evidence

- GitHub main branch GET: `protected: true` (or verify the effective ruleset using the ruleset API where supported).
- GitHub ruleset list: a ruleset with `enforcement: active` and target `main`.
- Create a **docs-only PR** and confirm `main-write-guard` is reported and passes. The PR must be mergeable through the normal reviewed path, but a direct main push must be blocked.
- Confirm Kalman builds continue to open draft PRs on **feature branches**, not write to `main`.
- Confirm the CKD status publisher still writes exclusively to **`research-status`**, and that sales/research scheduled workflows are not interrupted.
- Record the ruleset ID, effective configuration, run URLs and timestamp in [Issue #933](https://github.com/kimtk94/Codex/issues/933).

## Operating boundaries

Do **not** run a destructive main-push smoke test or grant an administrator token to GitHub Actions just to create rulesets. Admin configuration is intentionally an explicit owner action because the linked GitHub integration cannot edit branch protections (403).

If a check is stuck in Pending, inspect event/paths filters before making it required. If `main-write-guard` fails, open its artifact and correct the reported write pattern by PR; do not bypass the rule to force-merge. A commit message that intentionally skips CI can also prevent the required check from completing.

**Status:** HOLD until the owner activates and verifies the effective protection. A static-audit PASS alone does not close this issue.
