#!/usr/bin/env python3
from __future__ import annotations

import json
import operator
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT = Path("/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging")
PANEL = Path("/srv/is-analysis/results/multi_organ_aging/stage1_panel/LONGITUDINAL_ORGAN_PANEL.tsv.gz")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage5_outcomes")
CFG = yaml.safe_load((PROJECT / "config/organ_panels.yaml").read_text())

OPS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
}


def parse_rule(rule: str):
    m = re.match(r"^\s*(<=|>=|==|<|>)\s*(-?\d+(?:\.\d+)?)\s*$", str(rule))
    if not m:
        raise ValueError(f"Unsupported rule: {rule}")
    return OPS[m.group(1)], float(m.group(2))


def eval_rule(value, rule):
    if pd.isna(value):
        return None
    fn, threshold = parse_rule(rule)
    return bool(fn(float(value), threshold))


def baseline_row(g):
    return g.sort_values("visit_index").iloc[0]


def outcome_from_components(g, components):
    b = baseline_row(g)
    follow = g[g["visit_index"] > b["visit_index"]]
    if follow.empty:
        return np.nan, np.nan

    baseline_ok = []
    for comp in components:
        var = comp["variable"]
        if var not in g.columns:
            return np.nan, np.nan
        baseline_ok.append(eval_rule(b[var], comp["baseline_rule"]))
    if any(x is None for x in baseline_ok) or not all(baseline_ok):
        return np.nan, np.nan

    for _, row in follow.sort_values("visit_index").iterrows():
        event_flags = [eval_rule(row[c["variable"]], c["event_rule"]) for c in components]
        if any(x is True for x in event_flags):
            return 1.0, float(row["visit_index"])

    observable = False
    for _, row in follow.iterrows():
        for comp in components:
            if pd.notna(row[comp["variable"]]):
                observable = True
                break
        if observable:
            break
    return (0.0, np.nan) if observable else (np.nan, np.nan)


OUT.mkdir(parents=True, exist_ok=True)
panel = pd.read_csv(PANEL, sep="\t", low_memory=False)

rows = []
continuous_vars = ["EGFR", "GLUCOSE", "HBA1C", "SBP", "DBP", "ALT", "AST", "BMI"]

for sid, g in panel.groupby("subject_id"):
    g = g.sort_values("visit_index")
    b = g.iloc[0]
    last = g.iloc[-1]
    rec = {
        "subject_id": sid,
        "baseline_AGE": b.get("AGE", np.nan),
        "baseline_SEX": b.get("SEX", np.nan),
        "baseline_BMI": b.get("BMI", np.nan),
        "n_visits": int(len(g)),
        "last_visit": float(last["visit_index"]),
    }

    event_count = 0
    observed_count = 0
    for name, spec in CFG.get("outcomes", {}).items():
        components = spec.get("any_of")
        if components is None:
            components = [spec]
        event, visit = outcome_from_components(g, components)
        rec[f"incident_{name}"] = event
        rec[f"incident_{name}_visit"] = visit
        if pd.notna(event):
            observed_count += 1
            event_count += int(event)

    rec["multi_organ_incident_count"] = float(event_count) if observed_count else np.nan

    for var in continuous_vars:
        if var in g:
            first_valid = g[var].dropna()
            if len(first_valid):
                base_val = first_valid.iloc[0]
                last_val = first_valid.iloc[-1]
                rec[f"baseline_{var}"] = base_val
                rec[f"last_{var}"] = last_val
                rec[f"delta_{var}"] = last_val - base_val
            else:
                rec[f"baseline_{var}"] = np.nan
                rec[f"last_{var}"] = np.nan
                rec[f"delta_{var}"] = np.nan

    rows.append(rec)

out = pd.DataFrame(rows)
out.to_csv(OUT / "LONGITUDINAL_OUTCOMES.tsv.gz", sep="\t", index=False, compression="gzip")

incident_cols = [c for c in out.columns if c.startswith("incident_") and not c.endswith("_visit")]
qc = {
    "subjects": int(len(out)),
    "incident_outcomes": {
        c: {
            "observed": int(out[c].notna().sum()),
            "events": int(out[c].fillna(0).sum()),
        }
        for c in incident_cols
    },
}
(OUT / "STAGE5_OUTCOME_QC.json").write_text(json.dumps(qc, indent=2))
print(json.dumps(qc, indent=2))
