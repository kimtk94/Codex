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
SENSITIVE_PATH_PARTS = {"secrets", "credentials", ".ssh", ".aws", ".env"}
SENSITIVE_FILE_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"}
SENSITIVE_NAME_FRAGMENTS = ("secret", "credential", "password", "id_rsa")



def allowed_path(path: str) -> bool:
    """No global CSS/SFDC/Feishu, Vercel, secrets, infra or other files."""
    if not path or len(path.encode("utf-8")) > MAX_FILE_NAME_BYTES:
        return False
    if path.startswith("/") or "\\" in path:
        return False
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return False
    lowered = [part.casefold() for part in parts]
    filename = lowered[-1]
    if any(part in SENSITIVE_PATH_PARTS for part in lowered):
        return False
    if filename.startswith(".env") or any(word in filename for word in SENSITIVE_NAME_FRAGMENTS):
        return False
    if Path(filename).suffix in SENSITIVE_FILE_EXTENSIONS:
        return False
    if path in ALLOWED_EXACT or bool(WORKFLOW_PATTERN.fullmatch(path)):
        return True
    return path.startswith("local_ai/") and len(path) > len("local_ai/")


def evaluate(paths: list[str], changed_lines: int, pr_body: str, draft: bool) -> dict:
    failures: list[str] = []
    if not paths:
        failures.append("NO_CHANGED_FILES")
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
    task_match = TASK_ID.search(pr_body or "")
    criteria_match = ACCEPTANCE.search(pr_body or "")
    if not task_match:
        failures.append("TASK_ID_MISSING")
    if not criteria_match:
        failures.append("ACCEPTANCE_CRITERIA_MISSING")
    workflow_changed = any(p.startswith(".github/workflows/") for p in paths)
    # Safe, verifiable classification: not an approval or a review conclusion.
    return {
        "schema_version": 1,
        "scope_check": "PASS" if not failures else "FAIL",
        "review_decision": "HUMAN_REVIEW_REQUIRED" if not failures else "BLOCKED",
        "task_id": task_match.group(1) if task_match else None,
        "draft": bool(draft),
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
    # --no-renames makes both source and destination visible on file moves.
    # --numstat -z provides a numeric change count for every changed path and
    # explicitly marks binary changes as '-'. Do not silently count them as 0.
    raw = git_output(
        "diff", "--no-ext-diff", "--no-renames", "--numstat", "-z",
        diff_range, binary=True,
    )
    paths = []
    changed_lines = 0
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        fields = entry.split(b"\t", 2)
        if len(fields) != 3 or not fields[2]:
            raise ValueError("Unrecognized git diff numstat entry")
        added, deleted, name = fields
        if added == b"-" or deleted == b"-":
            raise ValueError("Binary changes require separate manual review")
        if not added.isdigit() or not deleted.isdigit():
            raise ValueError("Unrecognized git diff line counts")
        try:
            path = name.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("Non-UTF-8 file path is unsupported") from exc
        paths.append(path)
        changed_lines += int(added) + int(deleted)
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
