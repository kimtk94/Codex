from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    detect_wave,
    ensure_dir,
    egfr_2021,
    json_dump,
    list_input_files,
    load_config,
    normalize_sex,
    read_table,
    resolve_column,
    to_numeric,
    write_table,
)


def build_wave_frame(df: pd.DataFrame, wave: str, cfg: dict) -> tuple[pd.DataFrame, dict]:
    id_map = cfg["id_concepts"]
    concepts = cfg["concepts"]

    person_col = resolve_column(df.columns, id_map["person_id"])
    age_col = resolve_column(df.columns, id_map["age"])
    sex_col = resolve_column(df.columns, id_map["sex"])
    if person_col is None:
        raise ValueError(f"{wave}: no participant ID column resolved")

    out = pd.DataFrame(index=df.index)
    out["person_id"] = df[person_col].astype(str).str.strip()
    out["wave"] = wave
    out["visit_index"] = int(cfg["wave_order"].get(wave, 999))
    out["year_offset"] = float(cfg["wave_year_offset"].get(wave, np.nan))

    out["age"] = to_numeric(df[age_col]) if age_col is not None else np.nan
    out["sex_male"] = normalize_sex(df[sex_col]) if sex_col is not None else np.nan

    resolved = {"person_id": person_col, "age": age_col, "sex": sex_col}
    for concept, aliases in concepts.items():
        col = resolve_column(df.columns, aliases)
        resolved[concept] = col
        out[concept] = to_numeric(df[col]) if col is not None else np.nan

    if out["bmi"].notna().sum() == 0:
        h_m = out["height_cm"] / 100.0
        out["bmi"] = out["weight_kg"] / (h_m * h_m)

    out["pulse_pressure"] = out["sbp"] - out["dbp"]
    out["non_hdl"] = out["total_cholesterol"] - out["hdl"]

    valid_tyg = out["triglyceride"].gt(0) & out["glucose"].gt(0)
    out["tyg"] = np.nan
    out.loc[valid_tyg, "tyg"] = np.log(
        out.loc[valid_tyg, "triglyceride"] * out.loc[valid_tyg, "glucose"] / 2.0
    )

    out["egfr_2021"] = egfr_2021(out["creatinine"], out["age"], out["sex_male"])
    out["nlr"] = out["neutrophil"] / out["lymphocyte"].replace(0, np.nan)
    out["fev1_fvc"] = out["fev1"] / out["fvc"].replace(0, np.nan)

    out = out.replace([np.inf, -np.inf], np.nan)
    out = out[out["person_id"].ne("") & out["person_id"].ne("nan")].copy()
    return out, resolved


def main() -> int:
    ap = argparse.ArgumentParser(description="Build harmonized longitudinal multi-organ panel.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    input_dir = Path(args.input_dir or cfg["paths"]["input_dir"])
    out_root = Path(args.out_dir or cfg["paths"]["out_dir"])
    out = ensure_dir(out_root / "stage1_longitudinal")

    files = list_input_files(input_dir, cfg["file_globs"])
    frames = []
    mappings = []

    for p in files:
        wave = detect_wave(p, cfg["wave_order"])
        df = read_table(p)
        try:
            frame, resolved = build_wave_frame(df, wave, cfg)
        except ValueError as exc:
            print(f"[SKIP] {p}: {exc}")
            continue
        frame["source_file"] = str(p)
        frames.append(frame)
        for concept, col in resolved.items():
            mappings.append(
                {"wave": wave, "source_file": str(p), "concept": concept, "resolved_column": col}
            )

    if not frames:
        raise SystemExit("No wave could be harmonized.")

    long = pd.concat(frames, ignore_index=True, sort=False)

    def mode_or_nan(s: pd.Series):
        x = s.dropna()
        return x.mode().iloc[0] if not x.empty else np.nan

    long["sex_male"] = long.groupby("person_id")["sex_male"].transform(mode_or_nan)

    # Infer missing visit age from a subject-specific age-at-time-zero anchor:
    # observed age - planned visit offset. Median is used to tolerate integer age rounding.
    observed_age = long.loc[
        long["age"].notna() & long["year_offset"].notna(),
        ["person_id", "age", "year_offset"],
    ].copy()
    observed_age["age_at_offset0"] = observed_age["age"] - observed_age["year_offset"]
    anchor_map = observed_age.groupby("person_id")["age_at_offset0"].median().to_dict()

    anchor = long["person_id"].map(anchor_map)
    inferred_age = anchor + long["year_offset"]
    long["age_source"] = np.where(long["age"].notna(), "measured", "inferred_from_subject_anchor")
    long["age"] = long["age"].fillna(inferred_age)

    # QC: measured age should be close to the wave-based subject anchor.
    expected_age = anchor + long["year_offset"]
    long["age_wave_residual_years"] = np.where(
        long["age_source"].eq("measured"),
        long["age"] - expected_age,
        np.nan,
    )

    dup = long.duplicated(["person_id", "wave"], keep=False)
    dup_report = long.loc[dup, ["person_id", "wave", "source_file"]].copy()
    write_table(dup_report, out / "DUPLICATE_PARTICIPANT_WAVE.tsv")
    long = long.sort_values(["person_id", "visit_index", "source_file"]).drop_duplicates(
        ["person_id", "wave"], keep="first"
    )

    write_table(pd.DataFrame(mappings), out / "RESOLVED_VARIABLE_MAP.tsv")
    write_table(long, out / "LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz")
    try:
        write_table(long, out / "LONGITUDINAL_MULTI_ORGAN_PANEL.parquet")
    except Exception as exc:
        print(f"[WARN] parquet write skipped: {exc}")

    visits = long.groupby("person_id")["wave"].nunique()
    age_resid = pd.to_numeric(long["age_wave_residual_years"], errors="coerce").dropna()
    summary = {
        "rows": int(len(long)),
        "subjects": int(long["person_id"].nunique()),
        "waves": int(long["wave"].nunique()),
        "subjects_ge_3_visits": int((visits >= 3).sum()),
        "median_visits": float(visits.median()),
        "duplicate_rows_flagged": int(len(dup_report)),
        "measured_age_rows": int(long["age_source"].eq("measured").sum()),
        "inferred_age_rows": int(long["age_source"].eq("inferred_from_subject_anchor").sum()),
        "median_abs_age_wave_residual_years": float(age_resid.abs().median()) if len(age_resid) else None,
    }
    json_dump(summary, out / "STAGE1_SUMMARY.json")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
