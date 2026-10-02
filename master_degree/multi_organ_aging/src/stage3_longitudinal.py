from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from moa_common import save_json, slope_ols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--min-waves", type=int, default=2)
    args = ap.parse_args()

    df = pd.read_parquet(args.scores)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    organs = [c[:-5] for c in df.columns if c.endswith("__bag")]

    rows = []
    for sid, g in df.groupby("subject_id", sort=False):
        rec = {
            "subject_id": sid,
            "n_waves_total": int(g["wave"].nunique()),
            "baseline_age": float(g["age"].min()),
            "followup_years": float(g["years_since_baseline"].max()),
            "sex": g["sex"].dropna().iloc[0] if g["sex"].notna().any() else np.nan,
        }
        for organ in organs:
            c = f"{organ}__bag"
            d = g[["years_since_baseline", c]].dropna().sort_values(
                "years_since_baseline"
            )
            rec[f"{organ}__n_waves"] = len(d)
            rec[f"{organ}__bag_baseline"] = float(d[c].iloc[0]) if len(d) else np.nan
            rec[f"{organ}__bag_last"] = float(d[c].iloc[-1]) if len(d) else np.nan
            rec[f"{organ}__velocity"] = (
                slope_ols(d["years_since_baseline"], d[c])
                if len(d) >= args.min_waves else np.nan
            )
            rec[f"{organ}__delta"] = (
                float(d[c].iloc[-1] - d[c].iloc[0]) if len(d) >= 2 else np.nan
            )
        rows.append(rec)

    subj = pd.DataFrame(rows)
    subj.to_parquet(out / "STAGE3_SUBJECT_TRAJECTORIES.parquet", index=False)
    summary = {
        "n_subjects": len(subj),
        "organs": organs,
        "velocity_nonmissing": {
            o:int(subj[f"{o}__velocity"].notna().sum()) for o in organs
        },
    }
    save_json(summary, out / "STAGE3_SUMMARY.json")
    print(summary)


if __name__ == "__main__":
    main()
