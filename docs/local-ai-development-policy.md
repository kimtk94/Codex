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

## Review / promotion

1. Verify the PR task identifier and acceptance criteria.
2. Read the entire diff and identify unintended changes to operational code.
3. Check unit tests, Windows CI and evidence of actual behavior separately.
4. If the change touches a workflow, examine event triggers, permissions,
   third-party actions, artifacts, concurrency and any network calls.
5. Manually approve a PR only after independent assessment. Never infer
   approval from a green CI run or a Local AI-generated answer.

**Branch protection is not configured by this task.** Requiring this gate
for merge must be enabled by an authorized repository administrator.
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
