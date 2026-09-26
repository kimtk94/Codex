from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter

from moa_common import bh_fdr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phenotypes", required=True)
    ap.add_argument(
        "--outcomes", required=True,
        help="TSV with subject_id, duration, event and optional covariates"
    )
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--duration-col", default="duration")
    ap.add_argument("--event-col", default="event")
    args = ap.parse_args()

    ph = pd.read_parquet(args.phenotypes)
    oc = pd.read_csv(args.outcomes, sep="\t")
    df = ph.merge(oc, on="subject_id", how="inner")
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    exposures = [c for c in df.columns if c.endswith("__velocity_z")]
    exposures += [
        c for c in [
            "organ_velocity_mean_z",
            "organ_velocity_sd_z",
            "organ_velocity_range_z"
        ] if c in df
    ]
    base_covars = [
        c for c in ["baseline_age","sex_numeric","bmi","smoking"] if c in df
    ]

    rows = []
    for x in exposures:
        cols = [args.duration_col, args.event_col, x] + base_covars
        d = df[cols].replace([np.inf,-np.inf], np.nan).dropna()
        events = int(d[args.event_col].sum()) if len(d) else 0
        if len(d) < 100 or events < 20:
            rows.append({
                "exposure":x, "status":"insufficient",
                "n":len(d), "events":events
            })
            continue
        cph = CoxPHFitter()
        try:
            cph.fit(
                d, duration_col=args.duration_col,
                event_col=args.event_col
            )
            s = cph.summary.loc[x]
            rows.append({
                "exposure":x, "status":"ok",
                "n":len(d), "events":events,
                "coef":float(s["coef"]),
                "hr":float(s["exp(coef)"]),
                "ci_low":float(s["exp(coef) lower 95%"]),
                "ci_high":float(s["exp(coef) upper 95%"]),
                "p":float(s["p"]),
            })
        except Exception as e:
            rows.append({
                "exposure":x, "status":"error", "error":repr(e)
            })

    res = pd.DataFrame(rows)
    if "p" in res:
        res["q_bh"] = bh_fdr(res["p"].to_numpy())
    res.to_csv(out / "STAGE5_COX_RESULTS.tsv", sep="\t", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
