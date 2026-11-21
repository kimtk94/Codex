#!/usr/bin/env python3
"""Prepare Kalman manifest hotfix as a reviewed diff; never push to main.

Preview (default) only creates a patch and metadata on a GitHub-hosted runner.
--propose-pr requires explicit manual authorization and can push ONLY a new
proposal branch / draft PR. No customer data, broker state or live orders.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ALLOWED_FILES = (
    "kalman-hub-recovery/v7.4.20/source_manifest.ndjson",
    "kalman-hub-recovery/v7.4.20/build_report.json",
)
RUNTIME_SCRIPT = "kalman-toss-gateway/scripts/apply_runtime_hotfix_v7420.py"
MARKER = "KALMAN_DECISION_CONSOLE_HOTFIX_V7422"
APPROVAL_PHRASE = "APPROVE_RUNTIME_HOTFIX_PR"
BRANCH_RE = re.compile(r"^automation/kalman-hotfix-pr-[0-9]+$")


def run(*args: str, cwd: Path, env=None, capture: bool = True) -> str:
    completed = subprocess.run(
        list(args), cwd=str(cwd), env=env, check=True,
        capture_output=capture, text=True, timeout=120,
    )
    return completed.stdout.strip() if capture else ""


def verify_changed_paths(paths: list[str]) -> None:
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate changed paths")
    unexpected = sorted(set(paths) - set(ALLOWED_FILES))
    if unexpected:
        raise ValueError("Unexpected changed path(s): " + ", ".join(unexpected))


def authorize_proposal(env: dict[str, str]) -> str:
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise PermissionError("Draft PR proposal requires manual workflow_dispatch")
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise PermissionError("Draft PR proposal only runs on main workflow version")
    if env.get("GITHUB_ACTOR") != "kimtk94":
        raise PermissionError("Draft PR proposal limited to repository owner")
    if env.get("HOTFIX_PR_APPROVAL") != APPROVAL_PHRASE:
        raise PermissionError("Explicit approval phrase is required")
    rid = env.get("GITHUB_RUN_ID", "")
    if not rid.isdecimal() or len(rid) > 22:
        raise PermissionError("Invalid GitHub run ID")
    branch = "automation/kalman-hotfix-pr-" + rid
    if not BRANCH_RE.fullmatch(branch):
        raise PermissionError("Unsafe branch name")
    return branch


def prepare(root: Path, out_dir: Path) -> dict:
    root = root.resolve(strict=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Only run against a clean, trusted Git checkout, not an arbitrary workspace.
    if run("git", "status", "--porcelain", "--untracked-files=no", cwd=root):
        raise ValueError("Checkout has modifications before hotfix")
    run(sys.executable, RUNTIME_SCRIPT, cwd=root)
    manifest = root / ALLOWED_FILES[0]
    report_file = root / ALLOWED_FILES[1]
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    apps = [x for x in rows if x.get("file") == "app.js"]
    if len(apps) != 1:
        raise ValueError("Expected exactly one app.js manifest row")
    app = base64.b64decode(apps[0]["data_b64"], validate=True).decode("utf-8")
    if MARKER not in app:
        raise ValueError("Hotfix marker missing from built runtime app")
    with tempfile.TemporaryDirectory() as temp:
        generated_js = Path(temp) / "kalman-hotfix-app.js"
        generated_js.write_text(app, encoding="utf-8")
        run("node", "--check", str(generated_js), cwd=root)

    report = json.loads(report_file.read_text(encoding="utf-8"))
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if report.get("source_manifest_sha256") != digest:
        raise ValueError("Build report SHA does not match generated manifest")
    if report.get("runtime_hotfix_manifest_only") is not True:
        raise ValueError("Expected a manifest-only hotfix")
    paths = run("git", "diff", "--name-only", "--", cwd=root).splitlines()
    verify_changed_paths(paths)
    run("git", "diff", "--check", cwd=root)
    patch = run("git", "diff", "--binary", "--", *ALLOWED_FILES, cwd=root)
    (out_dir / "kalman-runtime-hotfix.patch").write_text(patch + ("\n" if patch else ""), encoding="utf-8")
    result = {
        "schema_version": 1,
        "decision": "HUMAN_REVIEW_REQUIRED" if paths else "NO_CHANGE",
        "source": "main",
        "changed_file_count": len(paths),
        "changed_paths": paths,
        "manifest_sha256": digest,
        "marker_verified": True,
        "node_syntax": "PASS",
        "direct_push_main": False,
        "pr_created": False,
    }
    (out_dir / "hotfix-preview.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def propose(root: Path, preview: dict, env: dict[str, str]) -> str:
    branch = authorize_proposal(env)
    if not preview["changed_paths"]:
        return "NO_CHANGE"
    # Only approved files, never an arbitrary git add -A.
    run("git", "config", "user.name", "github-actions[bot]", cwd=root)
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=root)
    run("git", "switch", "-c", branch, cwd=root)
    run("git", "add", "--", *ALLOWED_FILES, cwd=root)
    staged = run("git", "diff", "--cached", "--name-only", cwd=root).splitlines()
    verify_changed_paths(staged)
    if set(staged) != set(preview["changed_paths"]):
        raise ValueError("Staged files do not match validated proposal")
    run("git", "commit", "-m", "hotfix: propose v7.4.22 Kalman manifest (review only)", cwd=root)
    # Push only to a NEW proposal branch. Never use refs/heads/main.
    run("git", "push", "origin", "HEAD:refs/heads/" + branch, cwd=root)
    body = (
        "Generated from manual workflow_dispatch with explicit owner approval.\n\n"
        "Review the generated manifest + build report before merging.\n"
        "No production rollout or main push was performed.\n"
        "GitHub GITHUB_TOKEN-created PR events may not trigger CI automatically; "
        "manually run the relevant checks before approval.\n"
    )
    run("gh", "pr", "create", "--base", "main", "--head", branch,
        "--title", "hotfix: review Kalman v7.4.22 runtime manifest",
        "--body", body, "--draft", cwd=root)
    return branch


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Safe Kalman hotfix preview and draft PR proposal")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--propose-pr", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.propose_pr:
            # Fail before generating or changing files if the event is unauthorized.
            authorize_proposal(os.environ)
        result = prepare(args.repo, args.out_dir)
        if args.propose_pr:
            branch = propose(args.repo.resolve(strict=True), result, os.environ)
            print("PROPOSAL_RESULT:", branch)
        else:
            print("PREVIEW_ONLY: no git push, no PR, no deployment")
        print("Decision:", result["decision"], "Changed:", result["changed_paths"])
        return 0
    except (OSError, ValueError, PermissionError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, UnicodeError, KeyError) as exc:
        print("Hotfix preparation blocked:", type(exc).__name__, str(exc)[:400], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
