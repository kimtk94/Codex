#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import yaml

PROJECT = Path("/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging")
DATA = Path("/srv/is-analysis/data/multi_organ_aging")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage0_audit")
CFG = yaml.safe_load((PROJECT / "config/organ_panels.yaml").read_text())

SEARCH_ROOTS = [
    DATA / "approved",
    DATA / "public_training",
    Path("/srv/is-analysis/data/metabolic_resilience/stage0_koges/public_training"),
    Path("/srv/is-analysis/data/ckd/stage4_koges/public_training"),
]
EXTS = {".csv", ".tsv", ".txt", ".gz", ".zip"}


def detect_visit(name: str) -> int | None:
    s = name.lower()
    if "baseline" in s:
        return 0
    m = re.search(r"(?:follow|visit|wave|f)[_-]?(\d{1,2})", s)
    if m:
        return int(m.group(1))
    return None


def read_head(path: Path, nrows: int = 20) -> pd.DataFrame:
    attempts = [
        dict(sep="\t", low_memory=False),
        dict(sep=",", low_memory=False),
        dict(sep=None, engine="python"),
    ]
    last = None
    for kwargs in attempts:
        try:
            df = pd.read_csv(path, nrows=nrows, **kwargs)
            if df.shape[1] > 1:
                return df
        except Exception as exc:
            last = exc
    raise RuntimeError(f"Cannot read {path}: {last}")


def first_match(columns, aliases):
    lut = {str(c).strip().lower(): c for c in columns}
    for a in aliases:
        if str(a).lower() in lut:
            return str(lut[str(a).lower()])
    return None


def canonical_presence(columns):
    out = {}
    for canonical, aliases in CFG["variables"].items():
        out[canonical] = first_match(columns, aliases)
    return out


OUT.mkdir(parents=True, exist_ok=True)
seen = set()
files = []
for root in SEARCH_ROOTS:
    if not root.exists():
        continue
    for p in root.rglob("*"):
        if p.is_file() and (p.suffix.lower() in EXTS or p.name.endswith((".tsv.gz", ".csv.gz", ".txt.gz"))):
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                files.append(p)

rows = []
presence_rows = []
for p in sorted(files):
    try:
        df = read_head(p)
        cols = [str(x) for x in df.columns]
        canonical = canonical_presence(cols)
        id_col = first_match(cols, CFG["id_aliases"])
        age_col = first_match(cols, CFG["age_aliases"])
        sex_col = first_match(cols, CFG["sex_aliases"])
        rows.append({
            "path": str(p),
            "file_name": p.name,
            "visit_index": detect_visit(p.name),
            "n_columns": len(cols),
            "id_column": id_col,
            "age_column": age_col,
            "sex_column": sex_col,
            "read_ok": 1,
            "error": "",
            "columns_preview": "|".join(cols[:60]),
        })
        x = {"path": str(p), "visit_index": detect_visit(p.name)}
        x.update({k: (v or "") for k, v in canonical.items()})
        presence_rows.append(x)
    except Exception as exc:
        rows.append({
            "path": str(p),
            "file_name": p.name,
            "visit_index": detect_visit(p.name),
            "n_columns": 0,
            "id_column": "",
            "age_column": "",
            "sex_column": "",
            "read_ok": 0,
            "error": str(exc)[:500],
            "columns_preview": "",
        })

audit = pd.DataFrame(rows)
presence = pd.DataFrame(presence_rows)
audit.to_csv(OUT / "KOGES_FILE_AUDIT.tsv", sep="\t", index=False)
presence.to_csv(OUT / "KOGES_VARIABLE_PRESENCE.tsv", sep="\t", index=False)

summary = {
    "files_scanned": int(len(audit)),
    "files_read_ok": int(audit["read_ok"].sum()) if len(audit) else 0,
    "visits_detected": sorted([int(x) for x in audit["visit_index"].dropna().unique()]) if len(audit) else [],
    "variable_file_counts": {
        c: int((presence[c].astype(str) != "").sum()) if c in presence else 0
        for c in CFG["variables"]
    },
}
(OUT / "STAGE0_AUDIT.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
