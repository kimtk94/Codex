from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from moa_common import load_yaml, robust_z, save_json


def classify(row, organs, cfg):
    vals = pd.Series(
        {o: row.get(f"{o}__velocity_z", np.nan) for o in organs},
        dtype=float
    ).dropna()
    if len(vals) < 2:
        return "insufficient"

    mean = vals.mean()
    sd = vals.std(ddof=0)

    if mean >= cfg["accelerated_mean_z"] and sd < cfg["discordant_sd_z"]:
        return "generalized_accelerated"
    if mean <= cfg["resilient_mean_z"] and sd < cfg["discordant_sd_z"]:
        return "generalized_resilient"

    if sd >= cfg["discordant_sd_z"]:
        for organ in ["renal","metabolic","hepatic","vascular"]:
            if organ in vals.index:
                others = vals.drop(organ)
                if len(others) and vals[organ] - others.mean() >= cfg["organ_first_delta_z"]:
                    return f"{organ}_first"
        return "discordant"

    return "concordant_average"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    df = pd.read_parquet(args.trajectories).copy()
    cfg = load_yaml(args.config)["discordance"]
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    organs = [c[:-10] for c in df.columns if c.endswith("__velocity")]
    for o in organs:
        df[f"{o}__velocity_z"] = robust_z(df[f"{o}__velocity"])

    zcols = [f"{o}__velocity_z" for o in organs]
    df["organ_velocity_mean_z"] = df[zcols].mean(axis=1, skipna=True)
    df["organ_velocity_sd_z"] = df[zcols].std(axis=1, ddof=0, skipna=True)
    df["organ_velocity_range_z"] = (
        df[zcols].max(axis=1, skipna=True) - df[zcols].min(axis=1, skipna=True)
    )
    df["n_organs_velocity"] = df[zcols].notna().sum(axis=1)

    for a,b in [
        ("renal","metabolic"),
        ("renal","hepatic"),
        ("vascular","metabolic"),
        ("hepatic","metabolic"),
    ]:
        ca, cb = f"{a}__velocity_z", f"{b}__velocity_z"
        if ca in df and cb in df:
            df[f"{a}_minus_{b}__velocity_z"] = df[ca] - df[cb]

    df["aging_class"] = df.apply(
        classify, axis=1, organs=organs, cfg=cfg
    )
    df.to_parquet(
        out / "STAGE4_DISCORDANCE_PHENOTYPES.parquet", index=False
    )
    df["aging_class"].value_counts(dropna=False).rename_axis(
        "aging_class"
    ).reset_index(name="n").to_csv(
        out / "STAGE4_CLASS_COUNTS.tsv", sep="\t", index=False
    )
    save_json({
        "n_subjects": len(df),
        "organs": organs,
        "n_with_2plus_organs": int((df["n_organs_velocity"] >= 2).sum()),
    }, out / "STAGE4_SUMMARY.json")
    print(df["aging_class"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
