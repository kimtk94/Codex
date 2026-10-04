#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path


KEY_PATTERNS = re.compile(
    r"(SUMMARY|DEFAULT|INTEGRATED|EVIDENCE|CANDIDATE|STATUS|QC|FAIL|PLAN|PROVENANCE)",
    re.I,
)
GENE_COLUMNS = ("gene_symbol", "gene", "protein", "target", "symbol")


def safe(value: str) -> str:
    value = re.sub(r'[^A-Za-z0-9._ -]+', '_', str(value)).strip(' .')
    return value or 'Unknown'


def human_size(n):
    n = int(n or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return f"{x:.1f} {u}" if u != "B" else f"{int(x)} B"
        x /= 1024


def mtime_iso(path: Path):
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    except Exception:
        return "-"


def list_files(root: Path):
    out = []
    for p in root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            try:
                st = p.stat()
                out.append((p, st.st_size, st.st_mtime))
            except OSError:
                pass
    return out


def truncate(v, n=80):
    s = str(v if v is not None else "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def table_preview(path: Path, max_rows=6, max_cols=12):
    suffix = path.suffix.lower()
    delimiter = "\t" if suffix in {".tsv", ".txt"} else ","
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            rd = csv.reader(fh, delimiter=delimiter)
            rows = []
            for i, row in enumerate(rd):
                rows.append(row[:max_cols])
                if i >= max_rows:
                    break
        if not rows:
            return []
        width = max(len(x) for x in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        header = [truncate(x, 40) or f"col{i+1}" for i, x in enumerate(rows[0])]
        out = [
            "| " + " | ".join(header) + " |",
            "|" + "|".join(["---"] * width) + "|",
        ]
        for row in rows[1:]:
            out.append("| " + " | ".join(truncate(x).replace("|", "/") for x in row) + " |")
        return out
    except Exception:
        return []


def json_preview(path: Path):
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        text = json.dumps(obj, ensure_ascii=False, indent=2)
        lines = text.splitlines()[:80]
        return ["```json", *lines, "```"]
    except Exception:
        return []


def preview(path: Path):
    if path.stat().st_size > 2_000_000:
        return []
    if path.suffix.lower() == ".json":
        return json_preview(path)
    if path.suffix.lower() in {".tsv", ".csv"}:
        return table_preview(path)
    if path.suffix.lower() in {".md", ".txt"} and path.stat().st_size <= 250_000:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:40]
            return ["```text", *lines, "```"]
        except Exception:
            return []
    return []


def read_dict_rows(path: Path, max_rows=500):
    if path.suffix.lower() not in {".tsv", ".csv"} or path.stat().st_size > 10_000_000:
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    out = []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            rd = csv.DictReader(fh, delimiter=delimiter)
            for i, row in enumerate(rd):
                out.append(dict(row))
                if i + 1 >= max_rows:
                    break
    except Exception:
        return []
    return out


def find_gene_column(row):
    lower = {str(k).lower(): k for k in row.keys()}
    for c in GENE_COLUMNS:
        if c in lower:
            return lower[c]
    return None


def reset_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_stage_note(stage_dir: Path, dest: Path, drive_root: Path):
    files = list_files(stage_dir)
    latest = max((x[2] for x in files), default=0)
    total_size = sum(x[1] for x in files)
    generated = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    rel_stage = stage_dir.relative_to(drive_root).as_posix()
    lines = [
        "---",
        "type: research_stage",
        "research: CKD",
        f"stage: {stage_dir.name}",
        f'source_path: "{stage_dir}"',
        f'generated_at: "{generated}"',
        f"file_count: {len(files)}",
        f"total_size_bytes: {total_size}",
        "---",
        "",
        f"# CKD — {stage_dir.name}",
        "",
        f"- Source: `{rel_stage}`",
        f"- Files: **{len(files)}**",
        f"- Total size: **{human_size(total_size)}**",
        f"- Latest modified: **{dt.datetime.fromtimestamp(latest, tz=dt.timezone.utc).astimezone().isoformat(timespec='seconds') if latest else '-'}**",
        "",
        "## Priority artifacts",
        "",
    ]

    priority = sorted(
        [x for x in files if KEY_PATTERNS.search(x[0].name)],
        key=lambda x: (0 if "INTEGRATED" in x[0].name.upper() else 1, x[0].name.lower()),
    )
    if not priority:
        lines.append("- No summary/QC/evidence artifact detected.")
    else:
        for p, size, _ in priority[:25]:
            lines.append(f"- `{p.relative_to(stage_dir).as_posix()}` — {human_size(size)}")

    for p, size, _ in priority[:8]:
        pv = preview(p)
        if pv:
            lines += ["", f"### {p.name}", "", *pv]

    lines += [
        "",
        "## All files",
        "",
        "| File | Size | Modified |",
        "|---|---:|---|",
    ]
    for p, size, _ in sorted(files, key=lambda x: x[0].relative_to(stage_dir).as_posix().lower()):
        lines.append(
            f"| `{p.relative_to(stage_dir).as_posix()}` | {human_size(size)} | {mtime_iso(p)} |"
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "stage": stage_dir.name,
        "file_count": len(files),
        "total_size": total_size,
        "latest": latest,
        "priority": [x[0] for x in priority],
    }


def load_candidate_seed(ckd_root: Path):
    preferred = [ckd_root / "stage2" / "stage2_candidates.tsv"]
    preferred += sorted(ckd_root.glob("thesis_ready*/CKD_THESIS_CANDIDATE_TABLE.tsv"), reverse=True)
    preferred += sorted(ckd_root.glob("thesis_ready*/CKD_9GENE_EVIDENCE_MATRIX.tsv"), reverse=True)

    for p in preferred:
        if not p.exists():
            continue
        data = read_dict_rows(p, max_rows=5000)
        if not data:
            continue
        gene_col = find_gene_column(data[0])
        if not gene_col:
            continue
        genes = []
        seen = set()
        for row in data:
            gene = str(row.get(gene_col) or "").strip()
            if not gene or len(gene) > 40 or gene in seen:
                continue
            seen.add(gene)
            genes.append(gene)
        if genes:
            return genes, p
    return [], None


def collect_candidates(ckd_root: Path, seed_genes):
    seed = set(seed_genes)
    rows_by_gene = defaultdict(list)
    interesting = []
    if not seed:
        return rows_by_gene, interesting

    for p in ckd_root.rglob("*.tsv"):
        if not KEY_PATTERNS.search(p.name):
            continue
        data = read_dict_rows(p, max_rows=5000)
        if not data:
            continue
        gene_col = find_gene_column(data[0])
        if not gene_col:
            continue
        matched = False
        for row in data:
            gene = str(row.get(gene_col) or "").strip()
            if gene not in seed:
                continue
            rows_by_gene[gene].append((p, row))
            matched = True
        if matched:
            interesting.append(p)

    for gene in seed_genes:
        rows_by_gene.setdefault(gene, [])
    return rows_by_gene, interesting


def write_candidate_notes(rows_by_gene, out_dir: Path, drive_root: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for gene, entries in rows_by_gene.items():
        lines = [
            "---",
            "type: research_candidate",
            "research: CKD",
            f"gene: {gene}",
            "---",
            "",
            f"# {gene}",
            "",
            "## Evidence records",
            "",
        ]
        for p, row in entries[:20]:
            lines += [f"### {p.name}", f"- Source: `{p.relative_to(drive_root).as_posix()}`"]
            for k, v in row.items():
                if v not in (None, ""):
                    lines.append(f"- {k}: {truncate(v, 180)}")
            lines.append("")
        (out_dir / f"{safe(gene)}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_research_index(research_root: Path):
    lines = ["# Research Index", "", "## Thesis main", ""]
    is_master = research_root / "IS" / "IS_MASTER.md"
    if is_master.exists():
        lines.append("- [[01_RESEARCH/IS/IS_MASTER|IS — Thesis main]]")
    else:
        lines.append("- IS master not generated yet.")

    lines += ["", "## Supporting research", ""]
    ckd = research_root / "CKD" / "CKD_MASTER.md"
    if ckd.exists():
        lines.append("- [[01_RESEARCH/CKD/CKD_MASTER|CKD — Secondary core]]")

    metabolic = research_root / "METABOLIC_RESILIENCE" / "METABOLIC_RESILIENCE_MASTER.md"
    if metabolic.exists():
        lines.append("- [[01_RESEARCH/METABOLIC_RESILIENCE/METABOLIC_RESILIENCE_MASTER|Metabolic Resilience]]")

    muscle = research_root / "MUSCLE" / "MUSCLE_MASTER.md"
    if muscle.exists():
        lines.append("- [[01_RESEARCH/MUSCLE/MUSCLE_MASTER|Muscle / Strength Research]]")

    legacy = research_root / "IS_Analysis_V3"
    legacy_notes = []
    if legacy.exists():
        for p in sorted(legacy.glob("*.md")):
            if p.stem.upper() in {"IS_MASTER", "MUSCLE_MASTER", "METABOLIC_RESILIENCE_MASTER"}:
                continue
            legacy_notes.append(p)
    if legacy_notes:
        lines += ["", "## Repository snapshots", ""]
        for p in legacy_notes:
            lines.append(f"- [[01_RESEARCH/IS_Analysis_V3/{p.stem}|IS_Analysis_V3 — {p.stem}]]")

    (research_root / "RESEARCH_INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_home(vault: Path):
    home = vault / "00_HOME" / "HOME.md"
    lines = [
        "# MasterOS",
        "",
        "## Research — Thesis main",
        "",
        "- [[01_RESEARCH/IS/IS_MASTER|Ischemic Stroke — Thesis Main]]",
        "- [[01_RESEARCH/RESEARCH_INDEX|Research Index]]",
        "",
        "## Supporting research",
        "",
        "- [[01_RESEARCH/CKD/CKD_MASTER|CKD — Secondary Core]]",
    ]
    metabolic = vault / "01_RESEARCH" / "METABOLIC_RESILIENCE" / "METABOLIC_RESILIENCE_MASTER.md"
    if metabolic.exists():
        lines.append("- [[01_RESEARCH/METABOLIC_RESILIENCE/METABOLIC_RESILIENCE_MASTER|Metabolic Resilience]]")
    muscle = vault / "01_RESEARCH" / "MUSCLE" / "MUSCLE_MASTER.md"
    if muscle.exists():
        lines.append("- [[01_RESEARCH/MUSCLE/MUSCLE_MASTER|Muscle / Strength Research]]")
    lines += [
        "",
        "## CSS",
        "",
        "- [[00_HOME/CSS_DASHBOARD|CSS Dashboard]]",
        "- [[00_HOME/NORMALIZATION_REPORT|CSS Normalization Report]]",
        "- [[02_CSS/Actions/OPEN_ACTIONS|CSS Action Queue]]",
        "",
        "## Source of truth",
        "",
        "- IS thesis master: IS_Analysis_V3/docs/IS_MASTER.md",
        "- CKD stage results: Google Drive IS_Analysis_V3/results/ckd",
        "- CSS current state: Novogene_All_Emails canonical Sheet tabs",
        "- CSS timeline/invoices: css_project_manager.sqlite3",
        "- This Vault is a generated knowledge layer; source systems remain authoritative.",
    ]
    home.parent.mkdir(parents=True, exist_ok=True)
    home.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(drive_root: Path, vault: Path):
    ckd_root = drive_root / "results" / "ckd"
    if not ckd_root.exists():
        raise SystemExit(f"CKD results not found: {ckd_root}")

    research_root = vault / "01_RESEARCH"
    ckd_out = research_root / "CKD"
    reset_dir(ckd_out)
    stages_out = ckd_out / "Stages"
    stages_out.mkdir(parents=True, exist_ok=True)

    stages = []
    for stage_dir in sorted([x for x in ckd_root.iterdir() if x.is_dir()], key=lambda x: x.name):
        result = write_stage_note(stage_dir, stages_out / f"{safe(stage_dir.name)}.md", drive_root)
        stages.append(result)

    seed_genes, seed_source = load_candidate_seed(ckd_root)
    if not seed_genes:
        raise SystemExit(
            "No CKD candidate seed found. Expected stage2/stage2_candidates.tsv "
            "or a thesis-ready 9-gene candidate table."
        )

    rows_by_gene, source_tables = collect_candidates(ckd_root, seed_genes)
    write_candidate_notes(rows_by_gene, ckd_out / "Candidates", drive_root)

    generated = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    master = [
        "---",
        "type: research_master",
        "research: CKD",
        f'source_path: "{ckd_root}"',
        f'generated_at: "{generated}"',
        "---",
        "",
        "# CKD MASTER",
        "",
        f"- Drive source: `{ckd_root}`",
        f"- Stages detected: **{len(stages)}**",
        f"- Candidate seed genes: **{len(seed_genes)}**",
        f"- Evidence-linked candidate genes: **{len(rows_by_gene)}**",
        f"- Candidate seed source: `{seed_source.relative_to(drive_root).as_posix()}`",
        "",
        "## Coverage",
        "",
        f"- Stage4 EAS: **{'detected' if any(x['stage'].startswith('stage4_eas') for x in stages) else 'not present in Drive'}**",
        f"- KoGES: **{'detected' if any('koges' in x['stage'].lower() for x in stages) else 'not present in Drive'}**",
        f"- Thesis-ready freeze: **{'detected' if any(x['stage'].startswith('thesis_ready') for x in stages) else 'not present in Drive'}**",
        "",
        "## Stages",
        "",
        "| Stage | Files | Size | Latest |",
        "|---|---:|---:|---|",
    ]
    for x in stages:
        latest = (
            dt.datetime.fromtimestamp(x["latest"], tz=dt.timezone.utc).astimezone().isoformat(timespec="seconds")
            if x["latest"]
            else "-"
        )
        master.append(
            f'| [[01_RESEARCH/CKD/Stages/{safe(x["stage"])}|{x["stage"]}]] | '
            f'{x["file_count"]} | {human_size(x["total_size"])} | {latest} |'
        )

    master += ["", "## Candidate genes", ""]
    if rows_by_gene:
        for gene in seed_genes:
            master.append(f"- [[01_RESEARCH/CKD/Candidates/{safe(gene)}|{gene}]] — {len(rows_by_gene[gene])} evidence records")
    else:
        master.append("- No gene-bearing summary/evidence table detected.")

    master += ["", "## Candidate source tables", ""]
    for p in sorted(source_tables):
        master.append(f"- `{p.relative_to(drive_root).as_posix()}`")

    (ckd_out / "CKD_MASTER.md").write_text("\n".join(master) + "\n", encoding="utf-8")
    update_research_index(research_root)
    update_home(vault)

    print(f"CKD stages generated: {len(stages)}")
    print(f"CKD candidate genes generated: {len(rows_by_gene)}")
    print(f"Research vault: {research_root}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive-root", default=os.environ.get("IS_ANALYSIS_DRIVE_ROOT", "/content/drive/MyDrive/IS_Analysis_V3"))
    ap.add_argument("--vault", default=os.environ.get("MASTEROS_VAULT", "/content/drive/MyDrive/MasterOS_Vault"))
    a = ap.parse_args()
    build(Path(a.drive_root), Path(a.vault))