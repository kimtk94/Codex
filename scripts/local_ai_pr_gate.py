#!/usr/bin/env python3
"""Read-only, LOCAL-AI-scoped PR size/evidence gate.

This gate is intentionally narrower than repository-wide CI. A PASS means
only that a small change is ready for HUMAN review; it never approves,
merges, pushes, deploys or authorizes autonomous model tool use.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_FILES = 6
MAX_LINES = 500
MAX_FILE_NAME_BYTES = 500
TASK_ID = re.compile(r"(?mi)^Task-ID:\s*(LOCAL-AI-\d{3,4})\s*$")
ACCEPTANCE = re.compile(r"(?mi)^Acceptance:\s*(.{12,250})\s*$")
SHA = re.compile(r"^[0-9a-f]{40}$")

ALLOWED_EXACT = {
    "scripts/local_ai_pr_gate.py",
    "scripts/test_local_ai_pr_gate.py",
    ".github/workflows/local-ai-pr-review-gate.yml",
    "docs/local-ai-development-policy.md",
}
WORKFLOW_PATTERN = re.compile(r"^\.github/workflows/local-ai-[a-z0-9-]+\.yml$")


def allowed_path(path: str) -> bool:
    """No global CSS/SFDC/Feishu, Vercel, secrets, infra or other files."""
    if not path or len(path.encode("utf-8")) > MAX_FILE_NAME_BYTES:
        return False
    if path.startswith("/") or "\\" in path:
        return False
    if any(part in {"", ".", ".."} for part in path.split("/")):
        return False
    if path in ALLOWED_EXACT or bool(WORKFLOW_PATTERN.fullmatch(path)):
        return True
    return path.startswith("local_ai/") and len(path) > len("local_ai/")


def is_local_ai_change(path: str) -> bool:
    """Conservative scope signal; the strict allowlist is applied separately."""
    return (
        path.startswith("local_ai")
        or path.startswith("scripts/local_ai_")
        or path.startswith("scripts/test_local_ai_")
        or path.startswith(".github/workflows/local-ai-")
        or path == "docs/local-ai-development-policy.md"
    )


def evaluate(paths: list[str], changed_lines: int, pr_body: str, draft: bool) -> dict:
    failures: list[str] = []
    # A required check must run for unrelated CSS/SFDC/Feishu PRs too.
    # Return NOT_APPLICABLE, not missing Task-ID or scope failure.
    unrelated = bool(paths) and not any(is_local_ai_change(p) for p in paths)
    if not paths:
        failures.append("NO_CHANGED_FILES")
    if not unrelated:
        if len(paths) > MAX_FILES:
            failures.append("TOO_MANY_FILES")
        if changed_lines > MAX_LINES:
            failures.append("TOO_MANY_CHANGED_LINES")
        if changed_lines < 0:
            failures.append("INVALID_LINE_COUNT")
        if len(paths) != len(set(paths)):
            failures.append("DUPLICATE_PATHS")
        if any(not allowed_path(path) for path in paths):
            failures.append("OUT_OF_SCOPE_PATH")
        if not TASK_ID.search(pr_body or ""):
            failures.append("TASK_ID_MISSING")
        if not ACCEPTANCE.search(pr_body or ""):
            failures.append("ACCEPTANCE_CRITERIA_MISSING")
    task_match = TASK_ID.search(pr_body or "")
    workflow_changed = not unrelated and any(p.startswith(".github/workflows/") for p in paths)
    # Safe, verifiable classification: not an approval or a review conclusion.
    return {
        "schema_version": 1,
        "scope_check": "PASS" if not failures else "FAIL",
        "review_decision": ("NOT_APPLICABLE" if unrelated else "HUMAN_REVIEW_REQUIRED") if not failures else "BLOCKED",
        "task_id": task_match.group(1) if task_match else None,
        "draft": bool(draft),
        "local_ai_change_detected": not unrelated,
        "changed_file_count": len(paths),
        "changed_line_count": changed_lines,
        "workflow_changed": workflow_changed,
        "additional_workflow_review_required": workflow_changed,
        "failures": failures,
        "limits": {"max_files": MAX_FILES, "max_changed_lines": MAX_LINES},
        "actions_performed": {
            "git_push": False,
            "pr_approval": False,
            "pr_merge": False,
            "deployment": False,
            "google_drive": False,
            "local_ollama_inference": False,
        },
    }


def git_output(*args: str, binary: bool = False):
    completed = subprocess.run(
        ["git", *args], capture_output=True, check=True, timeout=30
    )
    return completed.stdout if binary else completed.stdout.decode("utf-8", errors="replace")


def actual_diff(base_sha: str, head_sha: str) -> tuple[list[str], int]:
    if not SHA.fullmatch(base_sha.lower()) or not SHA.fullmatch(head_sha.lower()):
        raise ValueError("Base/head must be actual 40-character commit SHAs")
    diff_range = base_sha + "..." + head_sha
    raw = git_output("diff", "--name-only", "-z", diff_range, binary=True)
    paths = [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]
    stat = git_output("diff", "--shortstat", diff_range).strip()
    insert = re.search(r"(\d+) insertions?\(\+\)", stat)
    delete = re.search(r"(\d+) deletions?\(-\)", stat)
    changed_lines = (int(insert.group(1)) if insert else 0) + (int(delete.group(1)) if delete else 0)
    if paths and not stat:
        raise ValueError("Cannot determine changed lines")
    return paths, changed_lines


def load_event(path: Path) -> tuple[str, bool]:
    event = json.loads(path.read_text(encoding="utf-8"))
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        raise ValueError("Pull request event required")
    return str(pr.get("body") or ""), bool(pr.get("draft", True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local AI PR review-scope gate")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        body, draft = load_event(args.event)
        paths, changed_lines = actual_diff(args.base, args.head)
        result = evaluate(paths, changed_lines, body, draft)
    except (ValueError, OSError, json.JSONDecodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print("Gate input error:", type(exc).__name__, file=sys.stderr)
        result = evaluate([], 0, "", True)
        result["failures"] = ["GATE_INPUT_ERROR"]
        result["scope_check"] = "FAIL"
        result["review_decision"] = "BLOCKED"
    result["created_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    # Do not include PR body, raw paths, logs or any source file data in artifact.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Scope:", result["scope_check"], "| Decision:", result["review_decision"])
    print("Files:", result["changed_file_count"], "| Changed lines:", result["changed_line_count"])
    print("Reasons:", ",".join(result["failures"]) if result["failures"] else "none")
    print("Task-ID:", result["task_id"])
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        summary = (
            "### Local AI PR scope gate\n\n"
            + "| Check | Result |\n|---|---|\n"
            + "| Scope | " + result["scope_check"] + " |\n"
            + "| Review | " + result["review_decision"] + " |\n"
            + "| File count | " + str(result["changed_file_count"]) + " |\n"
            + "| Changed lines | " + str(result["changed_line_count"]) + " |\n"
            + "| Workflow manual audit | " + str(result["workflow_changed"]) + " |\n"
            + "\nNever auto-approve, auto-merge or deploy from this gate.\n"
        )
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(summary)
    return 0 if result["scope_check"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
