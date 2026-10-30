#!/usr/bin/env python3
"""Read-only CSS/Kalman monorepo change-scope gate.

This predicts which website source packages changed. Vercel project settings
and its deployment creation limits are verified separately: this script never
claims a deployment occurred, was skipped, or is READY.
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSS = "apps/css-sales-workspace"
KALMAN = "research/kalman_triple_barrier/web"
GLOBAL_FILES = {
    "package.json", "package-lock.json", "npm-shrinkwrap.json",
    ".npmrc", "vercel.json",
}


def classify_paths(paths, manifest):
    scopes = manifest.get("workspaces", [])
    if not isinstance(scopes, list) or len(scopes) != len(set(scopes)):
        raise ValueError("Invalid or repeated workspace paths")
    if CSS not in scopes or KALMAN not in scopes:
        raise ValueError("Missing CSS or Kalman web workspaces")
    if any((a != b and b.startswith(a + "/")) for a in scopes for b in scopes):
        raise ValueError("Nested npm workspaces are not supported by this gate")

    touched = set()
    unknown = []
    globals_ = []
    for candidate in paths:
        path = candidate.strip().replace("\\", "/")
        if not path:
            continue
        if path.startswith("/") or path.startswith("../") or "/../" in path:
            raise ValueError("Unsafe changed file path")
        if path in GLOBAL_FILES:
            globals_.append(path)
            continue
        scope = next((w for w in sorted(scopes, key=len, reverse=True)
                      if path == w or path.startswith(w + "/")), None)
        if scope:
            touched.add(scope)
        else:
            unknown.append(path)

    css = CSS in touched
    kalman = KALMAN in touched
    if globals_ or unknown:
        outcome = "GLOBAL_OR_UNSCOPED_REVIEW"
    elif css and kalman:
        outcome = "BOTH_WEB_APPS_CHANGED"
    elif css:
        outcome = "CSS_ONLY"
    elif kalman:
        outcome = "KALMAN_ONLY"
    elif touched:
        outcome = "SOURCE_ONLY"
    else:
        outcome = "NO_CHANGES"
    return {
        "outcome": outcome,
        "css_web_changed": css,
        "kalman_web_changed": kalman,
        "workspace_changes": sorted(touched),
        "root_global_files": sorted(set(globals_)),
        "unscoped_files": sorted(set(unknown)),
        "vercel_deployment_verified": False,
        "notes": "Read-only change classification; Vercel API status is separate.",
    }


def git_changed(base, head):
    if not base or not head or not all(c.isalnum() for c in base + head):
        raise ValueError("Invalid revision")
    raw = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", base, head, "--"], cwd=ROOT)
    return [p.decode("utf-8") for p in raw.split(b"\x00") if p]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    result = classify_paths(git_changed(args.base, args.head), manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    summary = pathlib.Path(__import__("os").environ.get("GITHUB_STEP_SUMMARY", "/dev/null"))
    with summary.open("a", encoding="utf-8") as dst:
        dst.write("## Monorepo Deployment Scope (prediction only)\n\n")
        dst.write(f"**{result['outcome']}** · CSS source changed: {result['css_web_changed']} · "
                  f"Kalman source changed: {result['kalman_web_changed']}\n\n")
        dst.write("No Vercel API deployment was created or verified by this gate.\n\n")
        for key in ("workspace_changes", "root_global_files", "unscoped_files"):
            if result[key]:
                dst.write(f"- {key}: {', '.join(result[key])}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
