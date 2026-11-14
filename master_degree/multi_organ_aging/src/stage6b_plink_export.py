from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phenotypes", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--id-map", help="Optional TSV with subject_id, FID, IID")
    args = ap.parse_args()

    df = pd.read_parquet(args.phenotypes).copy()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    if args.id_map:
        ids = pd.read_csv(args.id_map, sep="\t", dtype=str)
        required = {"subject_id", "FID", "IID"}
        missing = required - set(ids.columns)
        if missing:
            raise SystemExit(f"id-map missing columns: {sorted(missing)}")
        df = ids[["subject_id", "FID", "IID"]].merge(
            df, on="subject_id", how="inner"
        )
    else:
        df["FID"] = df["subject_id"].astype(str)
        df["IID"] = df["subject_id"].astype(str)

    phenotype_cols = [
        c for c in df.columns
        if c.endswith("__velocity_z")
        or c in {
            "organ_velocity_mean_z",
            "organ_velocity_sd_z",
            "organ_velocity_range_z",
        }
    ]

    pheno = df[["FID", "IID"] + phenotype_cols].copy()
    pheno = pheno.replace([np.inf, -np.inf], np.nan)
    pheno.to_csv(out / "STAGE6B_PLINK_PHENO.tsv", sep="\t", index=False, na_rep="NA")

    covar_cols = [c for c in ["baseline_age", "sex_numeric"] if c in df]
    covar = df[["FID", "IID"] + covar_cols].copy()
    covar.to_csv(out / "STAGE6B_PLINK_COVAR.tsv", sep="\t", index=False, na_rep="NA")

    manifest = pd.DataFrame({
        "phenotype": phenotype_cols,
        "nonmissing_n": [int(df[c].notna().sum()) for c in phenotype_cols],
    })
    manifest.to_csv(out / "STAGE6B_PHENOTYPE_MANIFEST.tsv", sep="\t", index=False)

    print(manifest.to_string(index=False))


if __name__ == "__main__":
    main()
