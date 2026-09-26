#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT = Path("/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging")
DATA = Path("/srv/is-analysis/data/multi_organ_aging")
AUDIT = Path("/srv/is-analysis/results/multi_organ_aging/stage0_audit/KOGES_FILE_AUDIT.tsv")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage1_panel")
CFG = yaml.safe_load((PROJECT / "config/organ_panels.yaml").read_text())
SPACING = float(CFG["project"]["wave_spacing_years"])


def first_match(columns, aliases):
    lut = {str(c).strip().lower(): c for c in columns}
    for a in aliases:
        if str(a).lower() in lut:
            return lut[str(a).lower()]
    return None


def read_table(path: Path) -> pd.DataFrame:
    for kwargs in ({"sep": "\t"}, {"sep": ","}, {"sep": None, "engine": "python"}):
        try:
            x = pd.read_csv(path, low_memory=False, **kwargs)
            if x.shape[1] > 1:
                return x
        except Exception:
            pass
    raise RuntimeError(f"Unable to parse {path}")


def choose_files(audit: pd.DataFrame) -> pd.DataFrame:
    x = audit[(audit["read_ok"] == 1) & audit["visit_index"].notna()].copy()
    if x.empty:
        raise RuntimeError("No visit-coded files found. Inspect stage0 audit.")
    # Prefer project-local approved/public files over fallback shared sources.
    x["priority"] = x["path"].map(
        lambda s: 0 if "/multi_organ_aging/approved/" in s
        else 1 if "/multi_organ_aging/public_training/" in s
        else 2
    )
    x = x.sort_values(["visit_index", "priority", "path"])
    return x.groupby("visit_index", as_index=False).first()


OUT.mkdir(parents=True, exist_ok=True)
audit = pd.read_csv(AUDIT, sep="\t")
selected = choose_files(audit)

parts = []
source_map = {}
for _, rec in selected.iterrows():
    visit = int(rec["visit_index"])
    path = Path(rec["path"])
    df = read_table(path)
    id_col = first_match(df.columns, CFG["id_aliases"])
    if id_col is None:
        print(f"[SKIP] no ID column: {path}")
        continue

    out = pd.DataFrame({"subject_id": df[id_col].astype(str).str.strip()})
    age_col = first_match(df.columns, CFG["age_aliases"])
    sex_col = first_match(df.columns, CFG["sex_aliases"])
    out["AGE"] = pd.to_numeric(df[age_col], errors="coerce") if age_col else np.nan
    out["SEX"] = df[sex_col].astype(str).str.strip() if sex_col else np.nan

    for canonical, aliases in CFG["variables"].items():
        src = first_match(df.columns, aliases)
        out[canonical] = pd.to_numeric(df[src], errors="coerce") if src else np.nan

    out["visit_index"] = visit
    out["time_years"] = visit * SPACING
    out["source_file"] = str(path)
    out = out[out["subject_id"].ne("") & out["subject_id"].ne("nan")]
    source_map[str(visit)] = str(path)
    parts.append(out)

if not parts:
    raise RuntimeError("No usable visit files after ID detection.")

panel = pd.concat(parts, ignore_index=True)

# Collapse accidental duplicate subject/visit rows using median for numeric fields.
numeric_cols = ["AGE"] + list(CFG["variables"].keys()) + ["visit_index", "time_years"]
numeric_cols = [c for c in numeric_cols if c in panel]
agg = {c: "median" for c in numeric_cols}
agg["SEX"] = "first"
agg["source_file"] = "first"
panel = panel.groupby(["subject_id", "visit_index"], as_index=False).agg(agg)

# Propagate invariant sex.
panel["SEX"] = panel.groupby("subject_id")["SEX"].transform(lambda s: s.dropna().iloc[0] if s.dropna().size else np.nan)

# Derive chronological age when follow-up age is absent.
baseline_age = (
    panel.sort_values("visit_index")
    .groupby("subject_id")["AGE"]
    .first()
)
panel["_baseline_age"] = panel["subject_id"].map(baseline_age)
panel["AGE"] = panel["AGE"].fillna(panel["_baseline_age"] + panel["time_years"])
panel.drop(columns="_baseline_age", inplace=True)

if {"SBP", "DBP"}.issubset(panel.columns):
    panel["PULSE_PRESSURE"] = panel["SBP"] - panel["DBP"]
    panel["MAP"] = panel["DBP"] + (panel["SBP"] - panel["DBP"]) / 3.0

panel = panel.sort_values(["subject_id", "visit_index"]).reset_index(drop=True)
panel.to_csv(OUT / "LONGITUDINAL_ORGAN_PANEL.tsv.gz", sep="\t", index=False, compression="gzip")

qc = {
    "subjects": int(panel["subject_id"].nunique()),
    "rows": int(len(panel)),
    "visits": sorted([int(x) for x in panel["visit_index"].dropna().unique()]),
    "rows_per_visit": {str(int(k)): int(v) for k, v in panel.groupby("visit_index").size().items()},
    "feature_nonmissing": {c: int(panel[c].notna().sum()) for c in panel.columns if c not in {"subject_id", "SEX", "source_file"}},
    "source_files": source_map,
}
(OUT / "STAGE1_PANEL_QC.json").write_text(json.dumps(qc, indent=2))
print(json.dumps(qc, indent=2))
