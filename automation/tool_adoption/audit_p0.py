#!/usr/bin/env python3
"""Read-only inventory of Kalman repository automation and agent tooling.

Run: python3 automation/tool_adoption/audit_p0.py --root . --output /tmp/kalman-tool-audit.json
No dependencies, network, credentials, or mutations of the inspected tree.
"""
import argparse
import json
from pathlib import Path

SIGNALS = {
    "codex": ("codex", ".codex"),
    "superpowers": ("superpowers",),
    "ecc": ("everything-claude-code", "ecc"),
    "n8n": ("n8n",),
    "openclaw": ("openclaw",),
    "browser_use": ("browser-use", "browser_use"),
    "markitdown": ("markitdown",),
    "graphify": ("graphify",),
    "harness": ("harness",),
    "ci": (".github/workflows/",),
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "tool_adoption"}
MAX_FILE_SIZE = 1024 * 1024
TEXT_EXTS = {".py", ".yml", ".yaml", ".toml", ".json", ".md", ".sh", ".txt", ".ini", ".cfg"}
EVIDENCE_LIMIT = 15


def inventory(root: Path):
    root = root.resolve(strict=True)
    found = {name: [] for name in SIGNALS}
    scanned = 0
    skipped_large = 0
    # Python os.walk permits pruning; never follow directory symlinks.
    import os
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(current) / d).is_symlink())
        for filename in sorted(files):
            path = Path(current) / filename
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            lower_rel = rel.lower()
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_SIZE:
                skipped_large += 1
                continue
            scanned += 1
            content = ""
            if (path.suffix.lower() in TEXT_EXTS or filename in {"Dockerfile", "Makefile"}) and not lower_rel.endswith("vercel_manifest.json"):
                try:
                    content = path.read_text(encoding="utf-8", errors="replace").lower()
                except OSError:
                    pass
            for name, terms in SIGNALS.items():
                path_match = any(term in lower_rel for term in terms)
                content_match = any(term in content for term in terms)
                if (path_match or content_match) and len(found[name]) < EVIDENCE_LIMIT:
                    found[name].append({"path": rel, "match": "path" if path_match else "content"})
    return {
        "schema_version": 1,
        "files_scanned": scanned,
        "large_files_skipped": skipped_large,
        "signals": {name: {"evidence": evidence, "detected": bool(evidence)} for name, evidence in found.items()},
        "interpretation": "Static text/path hints only; audit source directory and generated Vercel manifests excluded to reduce self-matches. No match does not prove absence; a match does not prove installation or operational use.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = inventory(Path(args.root))
    data = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        destination = Path(args.output).resolve()
        source = Path(args.root).resolve()
        if destination == source or source in destination.parents:
            parser.error("--output must be outside the inspected repository")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(data + "\n", encoding="utf-8")
    else:
        print(data)


if __name__ == "__main__":
    main()
