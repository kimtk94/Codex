from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    inp = Path(args.candidates)
    if not inp.exists():
        raise SystemExit(f"Candidate file not found: {inp}")

    df = pd.read_csv(inp, sep="\t")
    required = {"file", "organ", "feature", "column", "nonmissing_sample"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Candidate table missing columns: {sorted(missing)}")

    df["canonical"] = df["organ"].astype(str) + "__" + df["feature"].astype(str)
    df["nonmissing_sample"] = pd.to_numeric(
        df["nonmissing_sample"], errors="coerce"
    ).fillna(0)

    rows = []
    for (file_name, canonical), g in df.groupby(["file", "canonical"], sort=True):
        g = g.sort_values(
            ["nonmissing_sample", "column"],
            ascending=[False, True],
        )
        top = g.iloc[0]
        rows.append({
            "file_regex": "^" + re.escape(Path(str(file_name)).name) + "$",
            "wave": "",
            "canonical": canonical,
            "source_column": str(top["column"]),
            "unit": "",
            "approved": 0,
            "candidate_count": len(g),
            "top_nonmissing_sample": int(top["nonmissing_sample"]),
            "review_status": (
                "AMBIGUOUS_MULTIPLE_MATCHES"
                if len(g) > 1 else "SINGLE_AUTO_CANDIDATE"
            ),
            "notes": "Review variable definition and unit before setting approved=1",
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    res = pd.DataFrame(rows)
    res.to_csv(out, sep="\t", index=False)
    print({
        "rows": len(res),
        "ambiguous": int(
            res["review_status"].eq("AMBIGUOUS_MULTIPLE_MATCHES").sum()
        ) if not res.empty else 0,
        "out": str(out),
    })


if __name__ == "__main__":
    main()
