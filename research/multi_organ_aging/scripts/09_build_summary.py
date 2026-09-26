#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path("/srv/is-analysis/results/multi_organ_aging")
OUT = ROOT / "stage8_summary"
OUT.mkdir(parents=True, exist_ok=True)


def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


summary = {
    "stage0": load_json(ROOT / "stage0_audit/STAGE0_AUDIT.json"),
    "stage1": load_json(ROOT / "stage1_panel/STAGE1_PANEL_QC.json"),
    "stage2": load_json(ROOT / "stage2_organ_age/ORGAN_AGE_MODEL_QC.json"),
    "stage3": load_json(ROOT / "stage3_pace/STAGE3_PACE_QC.json"),
    "stage4": load_json(ROOT / "stage4_patterns/STAGE4_PATTERN_QC.json"),
    "stage5": load_json(ROOT / "stage5_outcomes/STAGE5_OUTCOME_QC.json"),
    "stage6": load_json(ROOT / "stage6_association/STAGE6_ASSOCIATION_QC.json"),
    "stage7": load_json(ROOT / "stage7_genetics/STAGE7_GENETICS_STATUS.json"),
}

assoc_path = ROOT / "stage6_association/AGING_OUTCOME_ASSOCIATIONS.tsv"
top = []
if assoc_path.exists():
    try:
        a = pd.read_csv(assoc_path, sep="\t")
        if len(a):
            cols = [c for c in ["model", "outcome", "exposure", "n", "effect", "ci_low", "ci_high", "p", "q_fdr"] if c in a]
            top = a.sort_values(["q_fdr", "p"], na_position="last").head(30)[cols].to_dict("records")
    except Exception:
        pass
summary["top_associations"] = top

(OUT / "MULTI_ORGAN_AGING_SUMMARY.json").write_text(json.dumps(summary, indent=2))

lines = [
    "# Multi-organ Aging — Pipeline Summary",
    "",
    "Generated automatically from stage QC files.",
    "",
    "## Cohort / panel",
    f"- Subjects: {summary.get('stage1', {}).get('subjects', 'NA')}",
    f"- Rows: {summary.get('stage1', {}).get('rows', 'NA')}",
    f"- Visits: {summary.get('stage1', {}).get('visits', 'NA')}",
    "",
    "## Organ-age models",
]
for organ, rec in summary.get("stage2", {}).items():
    if isinstance(rec, dict):
        lines.append(
            f"- {organ}: status={rec.get('status')} n={rec.get('n_train', 'NA')} "
            f"RMSE={rec.get('oof_rmse', 'NA')} features={rec.get('features', [])}"
        )

lines += [
    "",
    "## Longitudinal pace",
    f"- Subjects with pace: {summary.get('stage3', {}).get('subjects', 'NA')}",
    f"- Organs: {summary.get('stage3', {}).get('organs', 'NA')}",
    "",
    "## Cross-organ patterns",
    f"- Selected cluster k: {summary.get('stage4', {}).get('selected_k', 'NA')}",
    "",
    "## Outcome models",
    f"- Completed models: {summary.get('stage6', {}).get('models_completed', 'NA')}",
    "",
    "## Genetics",
    f"- Status: {summary.get('stage7', {}).get('status', 'NA')}",
    f"- Completed models: {summary.get('stage7', {}).get('models_completed', 'NA')}",
    "",
    "## Interpretation rule",
    "Public-training results validate code and phenotype construction only. Final biological or clinical claims require rerunning the frozen pipeline in the approved thesis dataset.",
]
(OUT / "MULTI_ORGAN_AGING_SUMMARY.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
