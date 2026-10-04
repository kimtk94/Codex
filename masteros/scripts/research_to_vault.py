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
            name_upper = src.name.upper()
            if name_upper == "IS_MASTER.MD":
                project = "IS"
                dest_dir = out / "IS"
                dest = dest_dir / "IS_MASTER.md"
            elif name_upper == "MUSCLE_MASTER.MD":
                project = "MUSCLE"
                dest_dir = out / "MUSCLE"
                dest = dest_dir / "MUSCLE_MASTER.md"
            elif name_upper == "METABOLIC_RESILIENCE_MASTER.MD":
                project = "METABOLIC_RESILIENCE"
                dest_dir = out / "METABOLIC_RESILIENCE"
                dest = dest_dir / "METABOLIC_RESILIENCE_MASTER.md"
            else:
                dest_dir = out / safe(project)
                dest = dest_dir / safe(src.name)
            dest_dir.mkdir(parents=True, exist_ok=True)
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
    lines = ["# Research Index", "", "## Thesis main", ""]
    priority = {"IS": 0, "CKD": 1, "METABOLIC_RESILIENCE": 2, "MUSCLE": 3}
    ordered = sorted(notes, key=lambda x: (priority.get(x[0], 99), x[0], x[1].as_posix()))
    for project, rel in ordered:
        if project == "IS":
            lines.append(f"- [[{rel.as_posix()}|IS — Thesis main]]")
    secondary = [(project, rel) for project, rel in ordered if project != "IS"]
    if secondary:
        lines += ["", "## Supporting research", ""]
        for project, rel in secondary:
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
