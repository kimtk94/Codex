from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phenotypes", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--min-followup", type=float, default=2.0)
    args = ap.parse_args()

    df = pd.read_parquet(args.phenotypes).copy()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    vel = [c for c in df.columns if c.endswith("__velocity")]
    vel_z = [c for c in df.columns if c.endswith("__velocity_z")]

    rows = []
    for c in vel:
        x = pd.to_numeric(df[c], errors="coerce")
        rows.append({
            "phenotype": c,
            "n": int(x.notna().sum()),
            "mean": float(x.mean()) if x.notna().any() else np.nan,
            "sd": float(x.std()) if x.notna().sum() > 1 else np.nan,
            "p01": float(x.quantile(0.01)) if x.notna().any() else np.nan,
            "p50": float(x.quantile(0.50)) if x.notna().any() else np.nan,
            "p99": float(x.quantile(0.99)) if x.notna().any() else np.nan,
        })

    pd.DataFrame(rows).to_csv(
        out / "STAGE4B_VELOCITY_DISTRIBUTIONS.tsv", sep="\t", index=False
    )

    if vel_z:
        corr = df[vel_z].corr(method="spearman")
        corr.to_csv(out / "STAGE4B_VELOCITY_SPEARMAN.tsv", sep="\t")

    flags = pd.DataFrame({"subject_id": df["subject_id"]})
    if "followup_years" in df:
        flags["short_followup"] = (
            pd.to_numeric(df["followup_years"], errors="coerce") < args.min_followup
        )
    if "n_organs_velocity" in df:
        flags["lt2_organs"] = df["n_organs_velocity"] < 2
    if "organ_velocity_sd_z" in df:
        x = pd.to_numeric(df["organ_velocity_sd_z"], errors="coerce")
        flags["discordance_extreme_top_1pct"] = x >= x.quantile(0.99)

    for c in vel_z:
        x = pd.to_numeric(df[c], errors="coerce")
        flags[f"{c}__extreme"] = x.abs() >= 5

    flag_cols = [c for c in flags.columns if c != "subject_id"]
    flags["any_qc_flag"] = flags[flag_cols].fillna(False).any(axis=1)
    flags.to_csv(out / "STAGE4B_SUBJECT_QC_FLAGS.tsv", sep="\t", index=False)

    print({
        "n_subjects": len(df),
        "n_any_qc_flag": int(flags["any_qc_flag"].sum()),
        "n_velocity_traits": len(vel),
    })


if __name__ == "__main__":
    main()
