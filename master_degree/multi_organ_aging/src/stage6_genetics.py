from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm

from moa_common import bh_fdr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phenotypes", required=True)
    ap.add_argument(
        "--prs", required=True,
        help="TSV: subject_id plus one or more PRS columns"
    )
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    ph = pd.read_parquet(args.phenotypes)
    prs = pd.read_csv(args.prs, sep="\t")
    df = ph.merge(prs, on="subject_id", how="inner")
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    prs_cols = [c for c in prs.columns if c != "subject_id"]
    outcomes = [c for c in ph.columns if c.endswith("__velocity_z")]
    outcomes += [
        c for c in ["organ_velocity_sd_z","organ_velocity_range_z"]
        if c in ph
    ]

    rows = []
    for p in prs_cols:
        for y in outcomes:
            d = df[[p,y,"baseline_age"]].replace(
                [np.inf,-np.inf], np.nan
            ).dropna()
            if len(d) < 100:
                continue
            sd = d[p].std(ddof=0)
            px = (d[p] - d[p].mean()) / (sd if sd and np.isfinite(sd) else 1.0)
            X = pd.DataFrame({
                "prs_z":px,
                "baseline_age":d["baseline_age"]
            })
            X = sm.add_constant(X)
            fit = sm.OLS(d[y], X).fit(cov_type="HC3")
            rows.append({
                "prs":p, "outcome":y, "n":len(d),
                "beta":float(fit.params["prs_z"]),
                "se":float(fit.bse["prs_z"]),
                "p":float(fit.pvalues["prs_z"]),
            })

    res = pd.DataFrame(rows)
    if not res.empty:
        res["q_bh"] = bh_fdr(res["p"].to_numpy())
    res.to_csv(
        out / "STAGE6_PRS_ASSOCIATIONS.tsv", sep="\t", index=False
    )
    print(res.head(50).to_string(index=False))


if __name__ == "__main__":
    main()
