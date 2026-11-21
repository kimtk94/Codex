#!/usr/bin/env python3
"""Hosted GitHub Actions proof-of-work for safe offline Local AI checks.

No model is run on GitHub-hosted runner; no Drive credentials are read.
The JSON contains only non-sensitive CI metadata and test outcomes.
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

from local_ai import ollama_client


def run_checks() -> tuple[dict, int]:
    commands = {
        "unit_tests": [sys.executable, "-m", "unittest", "discover", "-s", "local_ai/tests", "-v"],
        "python_syntax": [sys.executable, "-m", "compileall", "-q", "local_ai"],
    }
    checks = {}
    overall = 0
    for name, argv in commands.items():
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=180, check=False)
            combined = (p.stdout or "") + "\n" + (p.stderr or "")
            match = re.search(r"Ran (\d+) tests?", combined)
            checks[name] = {
                "status": "PASS" if p.returncode == 0 else "FAIL",
                "count": int(match.group(1)) if name == "unit_tests" and match else None,
            }
            if p.returncode:
                print("CHECK_FAIL", name, "exit", p.returncode, file=sys.stderr)
                print(combined[-3500:], file=sys.stderr)
                overall = 1
        except subprocess.TimeoutExpired:
            checks[name] = {"status": "FAIL", "reason": "TIMEOUT", "count": None}
            overall = 1

    ok = (
        ollama_client.DEFAULT_MODEL == "qwen25coder3b-16k:latest"
        and ollama_client.DEFAULT_CONTEXT == 16384
        and ollama_client.MAX_INPUT_CHARS <= 6000
    )
    checks["local_model_defaults"] = {
        "status": "PASS" if ok else "FAIL",
        "expected_model": "qwen25coder3b-16k:latest",
        "expected_context_tokens": 16384,
        "max_input_chars": ollama_client.MAX_INPUT_CHARS,
    }
    if not ok:
        overall = 1
    return checks, overall


def build_report(checks: dict, exit_code: int) -> dict:
    sha = os.getenv("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha.lower()):
        sha = "NOT_AVAILABLE"
    event = os.getenv("GITHUB_EVENT_NAME", "")
    if event not in {"pull_request", "schedule", "workflow_dispatch", "push"}:
        event = "LOCAL"
    return {
        "schema_version": 1,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": "kimtk94/Codex",
        "source_sha": sha,
        "event": event,
        "overall": "PASS" if exit_code == 0 else "FAIL",
        "checks": checks,
        "real_world_not_verified": {
            "windows_laptop_ollama_inference": "NOT_CHECKED",
            "windows_google_drive_desktop_sync": "PENDING",
            "google_drive_cloud_data_freshness": "NOT_CHECKED",
            "local_3b_codex_tool_use": "HOLD",
        },
        "execution": {
            "runner": "github-hosted",
            "customer_data": "NOT_ACCESSED",
            "drive_credentials": "NOT_USED",
            "real_model_inference": "NOT_RUN",
            "git_push_or_deployment": "NOT_PERFORMED",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write sanitized Local AI hosted CI evidence")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    checks, rc = run_checks()
    report = build_report(checks, rc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Local AI hosted CI status:", report["overall"])
    print("Evidence:", args.output)
    for name, outcome in checks.items():
        print(name, outcome["status"])
    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_file:
        summary = (
            "### Local AI / Offline CI\n\n"
            + "Overall: **" + report["overall"] + "** | Commit: " + report["source_sha"] + "\n\n"
            + "| Check | Status |\n|---|---|\n"
            + "".join("| " + name + " | " + value["status"] + " |\n" for name, value in checks.items())
            + "\n**Not verified:** Windows Ollama inference, Google Drive Desktop synchronization, "
              "cloud Drive freshness and autonomous 3B tool-calling.\n"
        )
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(summary)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
