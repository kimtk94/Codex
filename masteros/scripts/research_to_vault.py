#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import re
from pathlib import Path


def safe(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" .")
    return value or "Unknown"


def main(root: Path, vault: Path) -> None:
    out = vault / "01_RESEARCH"
    out.mkdir(parents=True, exist_ok=True)
    patterns = ["*MASTER*.md", "README.md", "*STATUS*.md"]
    seen = set()
    notes = []
    for pattern in patterns:
        for src in root.rglob(pattern):
            if src in seen or ".git" in src.parts or "node_modules" in src.parts:
                continue
            seen.add(src)
            try:
                rel = src.relative_to(root)
                text = src.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            project = rel.parts[0] if len(rel.parts) > 1 else root.name
            dest_dir = out / safe(project)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / safe(src.name)
            stamp = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
            header = (
                "---\n"
                "type: research_snapshot\n"
                f"source_path: \"{src}\"\n"
                f"generated_at: \"{stamp}\"\n"
                "generated: true\n"
                "---\n\n"
                f"> Generated snapshot of `{src}`. Edit the source repository, not this copy.\n\n"
            )
            dest.write_text(header + text, encoding="utf-8")
            notes.append((project, dest.relative_to(vault).with_suffix("")))
    lines = ["# Research Index", ""]
    for project, rel in sorted(notes):
        lines.append(f"- [[{rel.as_posix()}|{project} — {rel.name}]]")
    (out / "RESEARCH_INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Research snapshots generated: {len(notes)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("RESEARCH_ROOT", "/srv/is-analysis"))
    ap.add_argument("--vault", default=os.environ.get("MASTEROS_VAULT", "/srv/masteros/vault"))
    a = ap.parse_args()
    root = Path(a.root)
    if not root.exists():
        raise SystemExit(f"Research root not found: {root}")
    main(root, Path(a.vault))
