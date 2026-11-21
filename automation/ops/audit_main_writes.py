#!/usr/bin/env python3
"""Read-only inventory of workflow commands that may push directly to Git.

This is a textual risk audit, NOT proof that all push paths have been found.
External actions, scripts launched by workflows, and runtime-computed targets
need follow-up tracing. Never mutate a branch or call a network API.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

GIT_PUSH = re.compile(r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+push\b", re.IGNORECASE)
GH_REF_API = re.compile(r"\bgh\s+api\b.*(?:git/refs/heads/main|git/refs/heads/\$)", re.IGNORECASE)
CURL_REF_API = re.compile(r"\bcurl\b.*(?:git/refs/heads/main|git/refs/heads/\$)", re.IGNORECASE)
MAIN_TARGET = re.compile(r"\b(?:HEAD|[A-Za-z0-9_./-]+):(?:refs/heads/)?main\b|\b(?:origin|upstream)\s+main(?:\s|$)", re.IGNORECASE)
KNOWN_FEATURE = re.compile(r"\bHEAD:refs/heads/(?!main\b)[A-Za-z0-9_./-]+|\bHEAD:(?!main\b)[A-Za-z0-9_./-]+", re.IGNORECASE)
ALLOWED_SUFFIXES = (".yml", ".yaml")


def classify_line(line: str) -> str | None:
    code = line.strip()
    if not code or code.startswith("#"):
        return None
    # GitHub workflow display names/descriptions are YAML metadata, not shell
    # commands. Do not mistake "- name: Rebuild without Git push" for a push.
    if re.match(r"^(?:-\s*)?(?:name|description|display-name|run-name)\s*:", code, re.IGNORECASE):
        return None
    if GH_REF_API.search(code) or CURL_REF_API.search(code):
        return "REF_API_WRITE"
    if not GIT_PUSH.search(code):
        return None
    if MAIN_TARGET.search(code):
        return "CONFIRMED_MAIN_PUSH"
    if KNOWN_FEATURE.search(code):
        return "EXPLICIT_OTHER_BRANCH_PUSH"
    return "DYNAMIC_OR_UNKNOWN_PUSH"


def scan_workflows(root: Path) -> dict:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        raise ValueError("Workflow directory is missing")
    files = sorted(path for path in workflow_dir.iterdir()
                   if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES)
    if not files:
        raise ValueError("No workflow files found; cannot assert a clean inventory")
    findings = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            category = classify_line(line)
            if category:
                findings.append({"file": relative, "line": line_no, "classification": category})
    confirmed = sum(x["classification"] in ("CONFIRMED_MAIN_PUSH", "REF_API_WRITE") for x in findings)
    unknown = sum(x["classification"] == "DYNAMIC_OR_UNKNOWN_PUSH" for x in findings)
    return {
        "schema_version": 1,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "workflow_files_scanned": len(files),
        "classification": "HOLD" if confirmed or unknown else "INVENTORY_CLEAN",
        "direct_main_write_count": confirmed,
        "unknown_push_count": unknown,
        "other_branch_push_count": sum(x["classification"] == "EXPLICIT_OTHER_BRANCH_PUSH" for x in findings),
        "findings": findings,
        "limitations": [
            "Only literal Git shell commands in .github/workflows are inspected",
            "External actions and scripts called by workflows may write to Git and require manual review",
            "Dynamic or multiline shell commands may be missed or conservatively classified",
            "Passing this audit alone is insufficient to enable branch protection",
        ],
        "actions_performed": {
            "git_write": False,
            "branch_protection_mutation": False,
            "workflow_dispatch": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of GitHub Actions direct pushes")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        report = scan_workflows(root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("WORKFLOWS_SCANNED:", report["workflow_files_scanned"])
        print("DIRECT_MAIN_WRITES:", report["direct_main_write_count"])
        print("UNKNOWN_PUSHES:", report["unknown_push_count"])
        print("OTHER_BRANCH_PUSHES:", report["other_branch_push_count"])
        print("BRANCH_PROTECTION_READINESS:", report["classification"])
        for item in report["findings"]:
            print(item["classification"], item["file"] + ":" + str(item["line"]))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print("AUDIT_FAILED:", type(exc).__name__, str(exc)[:180])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
