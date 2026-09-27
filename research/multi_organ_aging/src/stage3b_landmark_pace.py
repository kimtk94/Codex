from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, LinearRegression

from common import ensure_dir, json_dump, load_config, write_table, zscore


def fit_slope(g: pd.DataFrame, min_visits: int, min_followup: float):
    d = g[["year_offset", "age_acceleration_z"]].dropna().sort_values("year_offset")
    if len(d) < min_visits:
        return None

    span = float(d["year_offset"].max() - d["year_offset"].min())
    if span < min_followup:
        return None

    x = (d["year_offset"] - d["year_offset"].min()).to_numpy(float).reshape(-1, 1)
    y = d["age_acceleration_z"].to_numpy(float)

    ols = LinearRegression().fit(x, y)
    try:
        hub = HuberRegressor(alpha=0.0, max_iter=500).fit(x, y)
        slope = float(hub.coef_[0])
    except Exception:
        slope = float(ols.coef_[0])

    pred = ols.predict(x)
    den = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum((y - pred) ** 2)) / den if den > 0 else np.nan

    return {
        "n_visits": int(len(d)),
        "followup_years": span,
        "baseline_accel_z": float(y[0]),
        "last_accel_z": float(y[-1]),
        "delta_accel_z": float(y[-1] - y[0]),
        "ols_slope_z_per_year": float(ols.coef_[0]),
        "huber_slope_z_per_year": slope,
        "ols_r2": r2,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Estimate pre-landmark organ aging pace.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--scores", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.out_dir or cfg["paths"]["out_dir"])
    src = Path(
        args.scores
        or root / "stage2_clocks" / "ORGAN_AGE_SCORES_LONG.tsv.gz"
    )
    out = ensure_dir(root / "stage3b_landmark_pace")

    lm = cfg["landmark"]
    cutoff = int(lm["exposure_max_visit_index"])
    min_visits = int(lm["exposure_min_visits"])
    min_followup = float(lm["exposure_min_followup_years"])

    s = pd.read_csv(src, sep="\t", compression="infer", low_memory=False)
    s = s[pd.to_numeric(s["visit_index"], errors="coerce").le(cutoff)].copy()

    rows = []
    for (pid, organ), g in s.groupby(["person_id", "organ"], sort=False):
        x = fit_slope(g, min_visits, min_followup)
        if x is None:
            continue
        x.update({"person_id": pid, "organ": organ})
        rows.append(x)

    if not rows:
        raise SystemExit("No subject-organ pair met landmark pace requirements.")

    p = pd.DataFrame(rows)
    p["pace_z_within_organ"] = np.nan

    for organ, idx in p.groupby("organ").groups.items():
        p.loc[idx, "pace_z_within_organ"] = zscore(
            p.loc[idx, "huber_slope_z_per_year"]
        ).to_numpy()

    wide = p.pivot_table(
        index="person_id",
        columns="organ",
        values="pace_z_within_organ",
        aggfunc="first",
    )

    summary = pd.DataFrame(index=wide.index)
    summary["n_organs"] = wide.notna().sum(axis=1)
    summary["mean_organ_pace_z"] = wide.mean(axis=1, skipna=True)
    summary["max_organ_pace_z"] = wide.max(axis=1, skipna=True)
    summary["min_organ_pace_z"] = wide.min(axis=1, skipna=True)
    summary["discordance_sd"] = wide.std(axis=1, skipna=True)
    summary["discordance_range"] = wide.max(axis=1, skipna=True) - wide.min(axis=1, skipna=True)
    summary["multi_organ_landmark_pace_z"] = zscore(summary["mean_organ_pace_z"])

    for organ in wide.columns:
        summary[f"{organ}_pace_z"] = wide[organ]

    # Starting organ state is retained so downstream models can test whether
    # longitudinal pace adds information beyond baseline organ acceleration.
    baseline_scores = (
        s[pd.to_numeric(s["visit_index"], errors="coerce").eq(0)]
        .pivot_table(
            index="person_id",
            columns="organ",
            values="age_acceleration_z",
            aggfunc="first",
        )
    )
    for organ in baseline_scores.columns:
        summary[f"{organ}_baseline_accel_z"] = baseline_scores[organ]

    summary = summary.reset_index()

    write_table(p, out / "LANDMARK_SUBJECT_ORGAN_PACE.tsv.gz")
    write_table(summary, out / "LANDMARK_SUBJECT_MULTI_ORGAN_SUMMARY.tsv.gz")

    info = {
        "status": "ok",
        "exposure_max_visit_index": cutoff,
        "min_visits": min_visits,
        "min_followup_years": min_followup,
        "subject_organ_rows": int(len(p)),
        "subjects": int(p["person_id"].nunique()),
        "organs": sorted(p["organ"].unique().tolist()),
        "subjects_with_all_available_organs": int(
            (summary["n_organs"] == len(wide.columns)).sum()
        ),
        "design": "Exposure window ends before post-landmark incident-outcome window.",
    }
    json_dump(info, out / "STAGE3B_LANDMARK_SUMMARY.json")
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
