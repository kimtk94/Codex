from __future__ import annotations

import argparse
import re
from pathlib import Path
import numpy as np
import pandas as pd

from moa_common import find_first_column, load_yaml, match_patterns, numeric_coerce, read_table_auto, save_json


def infer_wave(path: Path, regex: str, fallback: int) -> int:
    m = re.search(regex, path.name, flags=re.I)
    if not m:
        return fallback
    nums = re.findall(r"\d+", m.group(0))
    return int(nums[-1]) if nums else fallback


def choose_feature(df, patterns):
    hits = match_patterns(df.columns, patterns)
    if not hits:
        return None
    return sorted(
        hits,
        key=lambda c: pd.to_numeric(df[c], errors="coerce").notna().sum(),
        reverse=True,
    )[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    cfg = load_yaml(args.config)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(
        p for p in Path(args.input_dir).rglob("*")
        if p.is_file() and any(str(p).lower().endswith(x) for x in [
            ".txt", ".tsv", ".csv", ".txt.gz", ".tsv.gz", ".csv.gz", ".parquet"
        ])
    )

    frames, mapping = [], []
    for idx, p in enumerate(files):
        try:
            df = read_table_auto(p)
        except Exception:
            continue
        id_col = find_first_column(df.columns, cfg["project"]["id_col_candidates"])
        age_col = find_first_column(df.columns, cfg["project"]["age_candidates"])
        sex_col = find_first_column(df.columns, cfg["project"]["sex_candidates"])
        if id_col is None or age_col is None:
            continue

        wave = infer_wave(p, cfg["project"]["wave_regex"], idx)
        z = pd.DataFrame({
            "subject_id": df[id_col].astype(str).str.strip(),
            "wave": wave,
            "age": numeric_coerce(df[age_col]),
            "sex": df[sex_col].astype(str).str.strip() if sex_col else np.nan,
            "source_file": p.name,
        })

        for organ, spec in cfg["organ_domains"].items():
            for feature, pats in spec["patterns"].items():
                c = choose_feature(df, pats)
                canonical = f"{organ}__{feature}"
                if c is not None:
                    z[canonical] = numeric_coerce(df[c])
                    mapping.append({
                        "file": p.name, "wave": wave,
                        "canonical": canonical, "source_column": c
                    })
                else:
                    z[canonical] = np.nan
        frames.append(z)

    if not frames:
        raise SystemExit("No usable KoGES wave files with ID + age were found.")

    panel = pd.concat(frames, ignore_index=True)
    panel = panel[(panel["subject_id"] != "") & panel["age"].notna()].copy()
    panel = panel.sort_values(["subject_id","wave","age"]).drop_duplicates(
        ["subject_id","wave"], keep="last"
    )
    baseline_age = panel.groupby("subject_id")["age"].transform("min")
    panel["years_since_baseline"] = panel["age"] - baseline_age
    panel["n_waves_subject"] = panel.groupby("subject_id")["wave"].transform("nunique")

    panel.to_parquet(out / "STAGE1_LONG_PANEL.parquet", index=False)
    pd.DataFrame(mapping).to_csv(out / "STAGE1_VARIABLE_MAP.tsv", sep="\t", index=False)

    summary = {
        "n_rows": len(panel),
        "n_subjects": int(panel["subject_id"].nunique()),
        "median_waves": float(panel.groupby("subject_id")["wave"].nunique().median()),
        "max_waves": int(panel.groupby("subject_id")["wave"].nunique().max()),
    }
    save_json(summary, out / "STAGE1_SUMMARY.json")
    print(summary)


if __name__ == "__main__":
    main()
