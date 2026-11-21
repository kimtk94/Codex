# Local AI development: small PR review protocol

This policy applies to **Local AI changes only**. It does not authorize any
new Salesforce, CSS, Feishu, finance, deployments, Google Drive sync or cloud AI
tool access. Production workflows outside Local AI remain unchanged.

## Task format

Use one focused task per PR, identified in the PR description:

```text
Task-ID: LOCAL-AI-001
Acceptance: Local AI PR scope and test checks pass; reviewer confirms diff and intended behavior.
```

Both fields must be present. Each task must have explicit, reproducible
acceptance criteria, not merely "works" or "looks good".

## Automated gate

`.github/workflows/local-ai-pr-review-gate.yml` triggers on Local AI files
and only reads PR metadata and Git differences. It validates:

- A valid `LOCAL-AI-000`-style task identifier and an Acceptance statement.
- No more than **6 changed files** and **500 added + deleted lines**.
- Every file belongs under `local_ai/`, an explicitly allowed gate file, or
  an explicitly named `local-ai-*.yml` GitHub Actions workflow.
- Tests on an isolated synthetic Git repository pass.

Files outside those paths, including SFDC/CSS/Feishu/Revenue workflows,
are **not permitted** in a Local AI task PR. Workflow edits still require
separate manual inspection for permissions, triggers, access to secrets,
deployment effects and fork-trigger safety.

A successful gate means **HUMAN_REVIEW_REQUIRED**, never "approved" or
"safe to merge". The gate has `contents: read` permission, no PR-approval
write access, no merge/push operations, no external Drive connection, and no
autonomous model tool-calling. It records a short metadata-only JSON artifact
for 7 days without copying code, customer files or PR descriptions.

The workflow runs on **every pull request**, without path filters, so the
required check is never stuck Pending merely because a PR changes only
CSS/SFDC/Feishu code. Non-Local-AI-only PRs return **NOT_APPLICABLE**
without requiring a Local AI Task-ID. If a PR mixes Local AI and unrelated
files, it is still BLOCKED. Missing or invalid Local AI Task-ID or acceptance
criteria remain a failure for applicable PRs.

**Exact job/check context:** `Read-only change scope / no auto approval`.
Only consider requiring this context AFTER the finalized workflow has been
reviewed, merged to `main`, and tested on both unrelated and Local AI PRs.
Do not use a workflow path filter for a required check; GitHub leaves skipped
checks pending and can block unrelated work.

## Review / promotion

1. Verify the PR task identifier and acceptance criteria.
2. Read the entire diff and identify unintended changes to operational code.
3. Check unit tests, Windows CI and evidence of actual behavior separately.
4. If the change touches a workflow, examine event triggers, permissions,
   third-party actions, artifacts, concurrency and any network calls.
5. Manually approve a PR only after independent assessment. Never infer
   approval from a green CI run or a Local AI-generated answer.

**Current observed GitHub configuration (2026-11-21):** the public main
branch reports `protected=false` and repository rulesets are empty. The
connected GitHub app cannot read the administration-protected branch
protection details (403), and offers no administration mutation action.
This task does **not** change the repo's protection settings.

Repository owner manual setup, only after reviewing/merging the gate:
`https://github.com/kimtk94/Codex/settings/branches` →
`Add branch protection rule` → branch `main` → require pull requests
and require status checks; select the exact GitHub Actions job name
`Read-only change scope / no auto approval` once it appears from a recent
run on `main`. Do not require reviewer approval if this is a sole-maintainer
repo with no second authorized reviewer; otherwise PRs may be impossible to
approve. Do not enable auto-merge, and test one unrelated PR before enforcing.

**Approval remains human-controlled.** Neither CI success nor this
configuration is a substitute for reviewing code and workflows. Branch
protection/rulesets affect ALL main PRs, so review existing automation
dependencies and check their impact before activation.

No automated code edits or PR merges are activated.

## Bootstrap PR #903

The original Local AI bootstrap is **42 changed files**, not a small task.
It intentionally remains Draft and should receive a separate full review
before any merger. Do not redefine a 42-file bootstrap as a 6-file task or
claim it passed the small-PR limit. The gate is designed for subsequent
small development changes.

## Environment status

Windows Git/gh and Ollama 16K model are verified; Drive for desktop remains
PENDING due to installer exit 1603 and lack of administrator elevation.
Qwen2.5-Coder 3B tool-calling is HOLD due to fabricated tool output.
Use GitHub-hosted Actions and deterministic scripts for validation until
those independent limitations are resolved.
