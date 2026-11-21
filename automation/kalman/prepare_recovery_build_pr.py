#!/usr/bin/env python3
"""Read-only preview or manually authorized draft PR for old Kalman hub builds.

Converts historical build workflows from direct main pushes. Preview executes
existing build and report assertions; proposal pushes only a unique feature
branch and opens a DRAFT PR, never deploys or merges.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

VERSIONS = {
    "7420": {
        "builder": "kalman-toss-gateway/scripts/build_investment_hub_v7420_recovery.py",
        "target": "vNext.7.4.20",
        "max_compact": 180000,
        "assertions": {"api_functions": 12, "universe": True,
                       "command_center": True, "ledger_semantics": True,
                       "web_read_only": True},
    },
    "7421": {
        "builder": "kalman-toss-gateway/scripts/build_investment_hub_v7421_execution_console.py",
        "target": "vNext.7.4.21",
        "max_compact": 200000,
        "assertions": {"api_functions": 12, "auto_trade_console": True,
                       "server_bot_status": True, "fixed_krw_display": 5000,
                       "web_read_only": True},
    },
    "7422": {
        "builder": "kalman-toss-gateway/scripts/build_investment_hub_v7422_decision_console.py",
        "target": "vNext.7.4.22",
        "max_compact": 220000,
        "assertions": {"api_functions": 12, "decision_console": True,
                       "server_offline_graceful": True, "benchmark_panel": True,
                       "execution_ledger_panel": True, "web_read_only": True},
    },
}
APPROVAL = "APPROVE_KALMAN_BUILD_PR"


def files_for(version: str) -> list[str]:
    if version not in VERSIONS:
        raise ValueError("Unsupported legacy build version")
    base = f"kalman-hub-recovery/v7.4.{int(version[-2:])}"
    return [f"{base}/{file}" for file in
            ("source_manifest.ndjson", "vercel_manifest.json", "build_report.json")]


def run(root: Path, *cmd: str) -> str:
    p = subprocess.run(cmd, cwd=root, check=True, capture_output=True,
                       text=True, timeout=180)
    return p.stdout.strip()


def authorize(version: str, env: dict[str, str]) -> str:
    if version not in VERSIONS:
        raise PermissionError("Unexpected build version")
    if (env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or env.get("GITHUB_REF") != "refs/heads/main"
        or env.get("GITHUB_ACTOR") != "kimtk94"
        or env.get("LEGACY_BUILD_APPROVAL") != APPROVAL):
        raise PermissionError("Only a manual owner-approved main workflow can propose a PR")
    rid = env.get("GITHUB_RUN_ID", "")
    if not rid.isdecimal() or len(rid) > 22:
        raise PermissionError("Invalid GitHub run identifier")
    return f"automation/kalman-build-{version}-pr-{rid}"


def check_changed(version: str, paths: list[str]) -> None:
    expected = set(files_for(version))
    if len(paths) != len(set(paths)) or any(path not in expected for path in paths):
        raise ValueError("Build touched unapproved files")


def preview(root: Path, version: str, out_dir: Path) -> dict:
    config = VERSIONS[version]
    root = root.resolve(strict=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    if run(root, "git", "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Checkout must start clean")
    allowed = files_for(version)
    tracked = run(root, "git", "ls-files", "--", *allowed).splitlines()
    if set(tracked) != set(allowed):
        raise ValueError("Missing tracked historical output")
    if version == "7420":
        # Same historical dependency as the existing v7.4.20 builder.
        run(root, "git", "fetch", "--no-tags", "origin",
            "feature/shadow-bakeoff-v1-20260913:refs/remotes/origin/feature/shadow-bakeoff-v1-20260913")
    run(root, sys.executable, config["builder"])
    report_path = root / allowed[-1]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("version") != config["target"]:
        raise ValueError("Historical version changed unexpectedly")
    for key, value in config["assertions"].items():
        if report.get(key) != value:
            raise ValueError("Build report contract failed: " + key)
    size = report.get("compact_manifest_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or not (0 < size < config["max_compact"]):
        raise ValueError("Compact manifest size outside expected bound")
    for file, field in ((allowed[0], "source_manifest_sha256"), (allowed[1], "vercel_manifest_sha256")):
        digest = hashlib.sha256((root / file).read_bytes()).hexdigest()
        if report.get(field) != digest:
            raise ValueError("Hash mismatch in generated manifest: " + file)
    changed = run(root, "git", "diff", "--name-only").splitlines()
    check_changed(version, changed)
    run(root, "git", "diff", "--check")
    patch = run(root, "git", "diff", "--binary", "--", *allowed)
    (out_dir / f"kalman-build-{version}.patch").write_text(
        patch + ("\n" if patch else ""), encoding="utf-8"
    )
    result = {
        "schema_version": 1,
        "build_version": config["target"],
        "decision": "HUMAN_REVIEW_REQUIRED" if changed else "NO_CHANGE",
        "changed_paths": changed,
        "compact_manifest_bytes": size,
        "source_manifest_sha256": report["source_manifest_sha256"],
        "vercel_manifest_sha256": report["vercel_manifest_sha256"],
        "direct_push_main": False,
        "draft_pr_created": False,
        "tests": "REPORT_HASH_AND_CONTRACT_PASS",
    }
    (out_dir / f"kalman-build-{version}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def propose(root: Path, version: str, report: dict, env: dict[str, str]) -> str:
    branch = authorize(version, env)
    if not report["changed_paths"]:
        return "NO_CHANGE"
    allowed = files_for(version)
    run(root, "git", "config", "user.name", "github-actions[bot]")
    run(root, "git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run(root, "git", "switch", "-c", branch)
    run(root, "git", "add", "--", *allowed)
    staged = run(root, "git", "diff", "--cached", "--name-only").splitlines()
    check_changed(version, staged)
    if set(staged) != set(report["changed_paths"]):
        raise ValueError("Staged files changed after validation")
    run(root, "git", "commit", "-m", f"build: propose historical Kalman {version} artifacts for review")
    run(root, "git", "push", "origin", "HEAD:refs/heads/" + branch)
    body = (
        "Manual owner-authorized Kalman historical build proposal.\n"
        "Only three versioned recovery artifacts may be modified.\n"
        "NO automatic main push, merge, deployment or live orders.\n"
        "Default GITHUB_TOKEN-created PRs may not trigger CI: manually run checks before merge.\n"
    )
    run(root, "gh", "pr", "create", "--base", "main", "--head", branch,
        "--title", f"build: review historical Kalman v7.4.{int(version[-2:])} recovery",
        "--body", body, "--draft")
    return branch


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Review-only Kalman historical build")
    parser.add_argument("--version", required=True, choices=sorted(VERSIONS))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--propose-pr", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.propose_pr:
            authorize(args.version, os.environ)
        report = preview(args.root, args.version, args.out_dir)
        if args.propose_pr:
            print("DRAFT_PR_RESULT:", propose(args.root.resolve(strict=True), args.version, report, os.environ))
        else:
            print("PREVIEW_ONLY: no Git writes")
        print("DECISION:", report["decision"], "VERSION:", args.version)
        return 0
    except (KeyError, ValueError, OSError, PermissionError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print("BLOCKED:", type(exc).__name__, str(exc)[:240], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
