from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from moa_common import load_yaml, save_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--min-waves", type=int, default=2)
    ap.add_argument("--high-confidence-waves", type=int, default=3)
    args = ap.parse_args()

    df = pd.read_parquet(args.panel)
    cfg = load_yaml(args.config)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    wave_rows = []
    for organ, spec in cfg["organ_domains"].items():
        cols = [c for c in df.columns if c.startswith(organ + "__")]
        if not cols:
            continue
        need = int(spec["required_min_features"])
        n_present = df[cols].notna().sum(axis=1)
        tmp = df[["subject_id", "wave", "age", "years_since_baseline"]].copy()
        tmp["organ"] = organ
        tmp["n_features_present"] = n_present
        tmp["organ_wave_usable"] = n_present >= need
        wave_rows.append(tmp)

    if not wave_rows:
        raise SystemExit("No organ feature columns were found in the panel.")

    long = pd.concat(wave_rows, ignore_index=True)
    long.to_csv(out / "STAGE1B_ORGAN_WAVE_COVERAGE.tsv", sep="\t", index=False)

    counts = (
        long[long["organ_wave_usable"]]
        .groupby(["subject_id", "organ"], as_index=False)
        .agg(
            usable_waves=("wave", "nunique"),
            min_age=("age", "min"),
            max_age=("age", "max"),
            followup_years=("years_since_baseline", "max"),
        )
    )
    counts["eligible_2plus"] = counts["usable_waves"] >= args.min_waves
    counts["eligible_3plus"] = counts["usable_waves"] >= args.high_confidence_waves
    counts.to_csv(out / "STAGE1B_SUBJECT_ORGAN_ELIGIBILITY.tsv", sep="\t", index=False)

    wide = counts.pivot(
        index="subject_id", columns="organ", values="usable_waves"
    ).fillna(0)
    wide.columns = [f"{c}__usable_waves" for c in wide.columns]
    wide = wide.reset_index()
    organ_wave_cols = [c for c in wide.columns if c.endswith("__usable_waves")]
    wide["n_organs_2plus"] = (wide[organ_wave_cols] >= args.min_waves).sum(axis=1)
    wide["n_organs_3plus"] = (
        wide[organ_wave_cols] >= args.high_confidence_waves
    ).sum(axis=1)
    wide.to_csv(out / "STAGE1B_SUBJECT_MULTI_ORGAN_ELIGIBILITY.tsv", sep="\t", index=False)

    summary = {
        "n_subjects": int(df["subject_id"].nunique()),
        "n_subjects_2plus_organs_2waves": int((wide["n_organs_2plus"] >= 2).sum()),
        "n_subjects_3plus_organs_2waves": int((wide["n_organs_2plus"] >= 3).sum()),
        "n_subjects_4organs_2waves": int((wide["n_organs_2plus"] >= 4).sum()),
        "n_subjects_2plus_organs_3waves": int((wide["n_organs_3plus"] >= 2).sum()),
    }
    save_json(summary, out / "STAGE1B_SUMMARY.json")
    print(summary)


if __name__ == "__main__":
    main()
