from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from moa_common import (
    find_first_column,
    load_yaml,
    match_patterns,
    numeric_coerce,
    read_table_auto,
    save_json,
)


def infer_wave(path: Path, regex: str, fallback: int) -> int:
    m = re.search(regex, path.name, flags=re.I)
    if not m:
        return fallback
    nums = re.findall(r"\d+", m.group(0))
    return int(nums[-1]) if nums else fallback


def choose_feature(df: pd.DataFrame, patterns: list[str]) -> str | None:
    hits = match_patterns(df.columns, patterns)
    if not hits:
        return None
    return sorted(
        hits,
        key=lambda c: pd.to_numeric(df[c], errors="coerce").notna().sum(),
        reverse=True,
    )[0]


def truthy(x) -> bool:
    return str(x).strip().lower() in {"1", "true", "yes", "y", "approved"}


def load_manual_map(path: str | None) -> pd.DataFrame | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Manual variable map does not exist: {p}")
    m = pd.read_csv(p, sep="\t", dtype=str).fillna("")
    required = {"canonical", "source_column"}
    missing = required - set(m.columns)
    if missing:
        raise SystemExit(f"Manual variable map missing columns: {sorted(missing)}")
    if "approved" in m.columns:
        m = m[m["approved"].map(truthy)].copy()
    if m.empty:
        raise SystemExit("Manual variable map has no approved rows.")
    return m


def manual_source(
    mapping: pd.DataFrame,
    file_name: str,
    wave: int,
    canonical: str,
) -> str | None:
    m = mapping[mapping["canonical"].eq(canonical)].copy()
    if m.empty:
        return None

    if "wave" in m.columns:
        exact = m[m["wave"].astype(str).isin({"", str(wave)})]
        if not exact.empty:
            m = exact

    if "file_regex" in m.columns:
        keep = []
        for _, row in m.iterrows():
            pat = str(row.get("file_regex", "")).strip()
            keep.append((not pat) or bool(re.search(pat, file_name, flags=re.I)))
        m = m.loc[keep]

    if m.empty:
        return None

    source = str(m.iloc[0]["source_column"]).strip()
    return source or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument(
        "--mapping",
        help="Reviewed TSV variable map. When supplied, organ biomarkers are mapped strictly from approved rows.",
    )
    args = ap.parse_args()

    cfg = load_yaml(args.config)
    manual_map = load_manual_map(args.mapping)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p for p in Path(args.input_dir).rglob("*")
        if p.is_file() and any(
            str(p).lower().endswith(x)
            for x in [
                ".txt", ".tsv", ".csv",
                ".txt.gz", ".tsv.gz", ".csv.gz", ".parquet",
            ]
        )
    )

    frames: list[pd.DataFrame] = []
    mapping_rows: list[dict] = []

    for idx, p in enumerate(files):
        try:
            df = read_table_auto(p)
        except Exception as e:
            mapping_rows.append({
                "file": p.name,
                "status": "read_error",
                "detail": repr(e),
            })
            continue

        id_col = find_first_column(df.columns, cfg["project"]["id_col_candidates"])
        age_col = find_first_column(df.columns, cfg["project"]["age_candidates"])
        sex_col = find_first_column(df.columns, cfg["project"]["sex_candidates"])
        if id_col is None or age_col is None:
            mapping_rows.append({
                "file": p.name,
                "status": "missing_id_or_age",
                "detail": f"id={id_col};age={age_col}",
            })
            continue

        wave = infer_wave(p, cfg["project"]["wave_regex"], idx)
        z = pd.DataFrame({
            "subject_id": df[id_col].astype(str).str.strip(),
            "wave": wave,
            "age": numeric_coerce(df[age_col]),
            "sex": (
                df[sex_col].astype(str).str.strip()
                if sex_col else np.nan
            ),
            "source_file": p.name,
        })

        for organ, spec in cfg["organ_domains"].items():
            for feature, patterns in spec["patterns"].items():
                canonical = f"{organ}__{feature}"

                if manual_map is not None:
                    source = manual_source(
                        manual_map, p.name, wave, canonical
                    )
                    mapping_source = "manual"
                else:
                    source = choose_feature(df, patterns)
                    mapping_source = "auto_discovery"

                if source is not None and source in df.columns:
                    z[canonical] = numeric_coerce(df[source])
                    status = "mapped"
                    nonmissing = int(z[canonical].notna().sum())
                else:
                    z[canonical] = np.nan
                    status = (
                        "source_column_missing"
                        if source is not None else "unmapped"
                    )
                    nonmissing = 0

                mapping_rows.append({
                    "file": p.name,
                    "wave": wave,
                    "canonical": canonical,
                    "source_column": source or "",
                    "mapping_source": mapping_source,
                    "status": status,
                    "nonmissing": nonmissing,
                })

        frames.append(z)

    if not frames:
        raise SystemExit("No usable KoGES wave files with ID + age were found.")

    panel = pd.concat(frames, ignore_index=True)
    panel = panel[
        (panel["subject_id"] != "") & panel["age"].notna()
    ].copy()
    panel = (
        panel.sort_values(["subject_id", "wave", "age"])
        .drop_duplicates(["subject_id", "wave"], keep="last")
    )

    baseline_age = panel.groupby("subject_id")["age"].transform("min")
    panel["years_since_baseline"] = panel["age"] - baseline_age
    panel["n_waves_subject"] = (
        panel.groupby("subject_id")["wave"].transform("nunique")
    )

    panel.to_parquet(out / "STAGE1_LONG_PANEL.parquet", index=False)
    pd.DataFrame(mapping_rows).to_csv(
        out / "STAGE1_VARIABLE_MAP.tsv", sep="\t", index=False
    )

    summary = {
        "n_rows": len(panel),
        "n_subjects": int(panel["subject_id"].nunique()),
        "median_waves": float(
            panel.groupby("subject_id")["wave"].nunique().median()
        ),
        "max_waves": int(
            panel.groupby("subject_id")["wave"].nunique().max()
        ),
        "mapping_mode": "manual_strict" if manual_map is not None else "auto_discovery",
        "manual_mapping_file": str(args.mapping) if args.mapping else None,
    }
    save_json(summary, out / "STAGE1_SUMMARY.json")
    print(summary)


if __name__ == "__main__":
    main()
