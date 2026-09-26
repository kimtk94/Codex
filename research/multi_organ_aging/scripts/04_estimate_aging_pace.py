#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import linregress

PROJECT = Path("/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging")
INFILE = Path("/srv/is-analysis/results/multi_organ_aging/stage2_organ_age/ORGAN_AGE_LONG.tsv.gz")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage3_pace")
CFG = yaml.safe_load((PROJECT / "config/organ_panels.yaml").read_text())
MIN_VISITS = int(CFG["project"]["minimum_visits_for_pace"])

OUT.mkdir(parents=True, exist_ok=True)
df = pd.read_csv(INFILE, sep="\t")

rows = []
for (sid, organ), g in df.groupby(["subject_id", "organ"]):
    g = g.dropna(subset=["time_years", "age_acceleration", "predicted_age"]).sort_values("time_years")
    if len(g) < MIN_VISITS or g["time_years"].nunique() < MIN_VISITS:
        continue

    acc = linregress(g["time_years"], g["age_acceleration"])
    pred = linregress(g["time_years"], g["predicted_age"])
    rows.append({
        "subject_id": sid,
        "organ": organ,
        "n_visits": int(len(g)),
        "followup_years": float(g["time_years"].max() - g["time_years"].min()),
        "acceleration_slope_per_year": float(acc.slope),
        "acceleration_slope_se": float(acc.stderr) if acc.stderr is not None else np.nan,
        "acceleration_slope_p": float(acc.pvalue),
        "predicted_age_pace_per_year": float(pred.slope),
        "predicted_age_pace_se": float(pred.stderr) if pred.stderr is not None else np.nan,
        "predicted_age_pace_p": float(pred.pvalue),
        "baseline_acceleration": float(g.iloc[0]["age_acceleration"]),
        "last_acceleration": float(g.iloc[-1]["age_acceleration"]),
        "delta_acceleration": float(g.iloc[-1]["age_acceleration"] - g.iloc[0]["age_acceleration"]),
    })

pace = pd.DataFrame(rows)
if pace.empty:
    raise RuntimeError("No subject-organ combinations met the minimum visit requirement.")

pace.to_csv(OUT / "ORGAN_AGING_PACE_LONG.tsv.gz", sep="\t", index=False, compression="gzip")

wide = pace.pivot(index="subject_id", columns="organ", values="acceleration_slope_per_year")
wide.columns = [f"{c}_accel_slope" for c in wide.columns]
wide.reset_index().to_csv(OUT / "ORGAN_AGING_PACE_WIDE.tsv.gz", sep="\t", index=False, compression="gzip")

qc = {
    "subject_organ_rows": int(len(pace)),
    "subjects": int(pace["subject_id"].nunique()),
    "organs": sorted(pace["organ"].unique().tolist()),
    "minimum_visits": MIN_VISITS,
    "median_followup_years": float(pace["followup_years"].median()),
}
(OUT / "STAGE3_PACE_QC.json").write_text(json.dumps(qc, indent=2))
print(json.dumps(qc, indent=2))
