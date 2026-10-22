from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from moa_common import load_yaml, match_patterns, read_table_auto, save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--sample-rows", type=int, default=2000)
    args = ap.parse_args()

    inp = Path(args.input_dir)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_yaml(args.config)

    files = sorted(
        p for p in inp.rglob("*")
        if p.is_file() and any(str(p).lower().endswith(x) for x in [
            ".tsv", ".txt", ".csv", ".tsv.gz", ".txt.gz", ".csv.gz",
            ".xlsx", ".xls", ".parquet"
        ])
    )

    inventory = []
    matches = []
    for p in files:
        try:
            df = read_table_auto(p, nrows=args.sample_rows)
            cols = list(map(str, df.columns))
            inventory.append({
                "file": str(p),
                "n_sample_rows": len(df),
                "n_columns": len(cols),
                "columns": "|".join(cols),
            })
            for organ, spec in cfg["organ_domains"].items():
                for feature, pats in spec["patterns"].items():
                    for col in match_patterns(cols, pats):
                        s = pd.to_numeric(df[col], errors="coerce")
                        matches.append({
                            "file": str(p),
                            "organ": organ,
                            "feature": feature,
                            "column": col,
                            "nonmissing_sample": int(s.notna().sum()),
                            "median_sample": float(s.median()) if s.notna().any() else None,
                        })
        except Exception as e:
            inventory.append({"file": str(p), "error": repr(e)})

    inv = pd.DataFrame(inventory)
    mat = pd.DataFrame(matches)
    inv.to_csv(out / "STAGE0_FILE_INVENTORY.tsv", sep="\t", index=False)
    mat.to_csv(out / "STAGE0_VARIABLE_CANDIDATES.tsv", sep="\t", index=False)

    summary = {
        "n_files": len(files),
        "n_files_read": int(inv["error"].isna().sum()) if "error" in inv else len(inv),
        "n_candidate_matches": len(mat),
        "organs": sorted(mat["organ"].dropna().unique().tolist()) if not mat.empty else [],
    }
    save_json(summary, out / "STAGE0_SUMMARY.json")
    print(summary)


if __name__ == "__main__":
    main()
