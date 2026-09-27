from __future__ import annotations

import argparse
import re
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
    norm_name,
    read_table,
    resolve_column,
    to_numeric,
    write_table,
)


def parse_visit_date(series: pd.Series) -> pd.Series:
    raw = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    try:
        out = pd.to_datetime(raw, errors="coerce", format="mixed")
    except TypeError:
        out = pd.to_datetime(raw, errors="coerce")

    ymd8 = raw.str.fullmatch(r"\d{8}", na=False)
    if ymd8.any():
        out.loc[ymd8] = pd.to_datetime(raw.loc[ymd8], format="%Y%m%d", errors="coerce")

    ymd6 = raw.str.fullmatch(r"\d{6}", na=False)
    if ymd6.any():
        out.loc[ymd6] = pd.to_datetime(
            raw.loc[ymd6] + "15", format="%Y%m%d", errors="coerce"
        )

    return out


def normalize_yes_no_1_2(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    return x.map({1.0: 0.0, 2.0: 1.0})


def cumulative_established_history(series: pd.Series) -> pd.Series:
    out = []
    established = 0.0
    seen = False
    for value in series:
        if pd.notna(value):
            seen = True
            if float(value) == 1.0:
                established = 1.0
        out.append(established if seen else np.nan)
    return pd.Series(out, index=series.index, dtype=float)


INTEGRATED_VISIT_RE = re.compile(r"^a(\\d{1,2})_(.+)$", re.IGNORECASE)


def integrated_wide_columns(columns) -> dict[int, list[str]]:
    """Group KoGES integrated-wide columns by A01/A02/... visit prefix."""
    waves: dict[int, list[str]] = {}
    for original in columns:
        m = INTEGRATED_VISIT_RE.match(norm_name(original))
        if m:
            waves.setdefault(int(m.group(1)), []).append(original)
    return waves


def integrated_visit_to_wave(visit_number: int) -> str:
    if visit_number < 1:
        raise ValueError(f"Invalid integrated visit number: {visit_number}")
    return "base" if visit_number == 1 else f"follow_{visit_number - 1:02d}"


def split_integrated_wide(
    df: pd.DataFrame,
    cfg: dict,
) -> list[tuple[str, pd.DataFrame]]:
    """Split one Axx-prefixed integrated KoGES table into canonical wave frames.

    Global participant ID / sex columns are copied into each temporary wave
    table when wave-specific versions are absent.
    """
    groups = integrated_wide_columns(df.columns)
    if len(groups) < 3:
        return []

    id_map = cfg["id_concepts"]
    global_columns = [
        c
        for c in df.columns
        if not INTEGRATED_VISIT_RE.match(norm_name(c))
    ]
    global_person = resolve_column(global_columns, id_map["person_id"])
    global_sex = resolve_column(global_columns, id_map["sex"])

    out: list[tuple[str, pd.DataFrame]] = []
    for visit_number in sorted(groups):
        wave = integrated_visit_to_wave(visit_number)
        if wave not in cfg["wave_order"]:
            print(
                f"[WARN] integrated visit A{visit_number:02d} has no configured "
                f"wave mapping; skipped"
            )
            continue

        cols = list(groups[visit_number])
        tmp = df[cols].copy()

        if global_person is not None and resolve_column(tmp.columns, id_map["person_id"]) is None:
            tmp[global_person] = df[global_person]

        if global_sex is not None and resolve_column(tmp.columns, id_map["sex"]) is None:
            tmp[global_sex] = df[global_sex]

        out.append((wave, tmp))

    return out


def first_nonmissing(series: pd.Series):
    x = series.dropna()
    return x.iloc[0] if not x.empty else np.nan


def coalesce_person_wave_rows(long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge duplicate person-wave rows from separate controlled-data tables.

    Public training usually contributes one row per person-wave. Controlled
    integrated exports may arrive as separate BIOCHEM / ANTHRO / SPIRO tables.
    This function preserves nonmissing values across those tables instead of
    silently dropping later rows. Conflicting nonmissing values are reported.
    """
    key = ["person_id", "wave"]
    duplicates = long.duplicated(key, keep=False)
    if not duplicates.any():
        return long.copy(), pd.DataFrame(
            columns=["person_id", "wave", "column", "n_distinct", "values_preview"]
        )

    conflicts = []
    value_cols = [
        c
        for c in long.columns
        if c not in {"person_id", "wave", "source_file", "source_mode"}
    ]

    for (pid, wave), g in long.loc[duplicates].groupby(key, sort=False):
        for col in value_cols:
            vals = g[col].dropna()
            if vals.empty:
                continue
            distinct = pd.unique(vals.astype(str))
            if len(distinct) > 1:
                conflicts.append(
                    {
                        "person_id": pid,
                        "wave": wave,
                        "column": col,
                        "n_distinct": int(len(distinct)),
                        "values_preview": "|".join(distinct[:5]),
                    }
                )

    rows = []
    for (pid, wave), g in long.groupby(key, sort=False):
        row = {"person_id": pid, "wave": wave}
        for col in long.columns:
            if col in key:
                continue
            if col == "source_file":
                row[col] = ";".join(dict.fromkeys(g[col].dropna().astype(str)))
            elif col == "source_mode":
                row[col] = ";".join(dict.fromkeys(g[col].dropna().astype(str)))
            else:
                row[col] = first_nonmissing(g[col])
        rows.append(row)

    merged = pd.DataFrame(rows)
    return merged, pd.DataFrame(conflicts)


def build_wave_frame(df: pd.DataFrame, wave: str, cfg: dict) -> tuple[pd.DataFrame, dict]:
    id_map = cfg["id_concepts"]
    concepts = cfg["concepts"]

    person_col = resolve_column(df.columns, id_map["person_id"])
    age_col = resolve_column(df.columns, id_map["age"])
    sex_col = resolve_column(df.columns, id_map["sex"])
    visit_date_col = resolve_column(df.columns, id_map.get("visit_date", []))
    if person_col is None:
        raise ValueError(f"{wave}: no participant ID column resolved")

    out = pd.DataFrame(index=df.index)
    out["person_id"] = df[person_col].astype(str).str.strip()
    out["wave"] = wave
    out["visit_index"] = int(cfg["wave_order"].get(wave, 999))
    out["year_offset_planned"] = float(cfg["wave_year_offset"].get(wave, np.nan))
    out["year_offset"] = out["year_offset_planned"]
    out["visit_date"] = (
        parse_visit_date(df[visit_date_col])
        if visit_date_col is not None
        else pd.NaT
    )

    out["age"] = to_numeric(df[age_col]) if age_col is not None else np.nan
    out["sex_male"] = normalize_sex(df[sex_col]) if sex_col is not None else np.nan

    resolved = {
        "person_id": person_col,
        "age": age_col,
        "sex": sex_col,
        "visit_date": visit_date_col,
    }
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

    # KoGES yes/no disease-history items use 1=no, 2=yes. Preserve the raw
    # numeric code and expose a 0/1 analysis variable.
    for concept in cfg.get("binary_coding", {}).get("variables", []):
        if concept not in out.columns:
            continue
        out[f"{concept}_raw_code"] = out[concept].copy()
        out[concept] = normalize_yes_no_1_2(out[concept])

    # Apply deliberately broad physiologic bounds after sentinel removal.
    # Values outside these ranges are treated as QC failures, not winsorized,
    # so the raw export can always be revisited.
    for concept, bounds in cfg.get("plausible_ranges", {}).items():
        if concept not in out.columns:
            continue
        lo, hi = map(float, bounds)
        x = pd.to_numeric(out[concept], errors="coerce")
        out[concept] = x.where(x.between(lo, hi))

    # Recompute derived features after range masking.
    h_m = out["height_cm"] / 100.0
    derived_bmi = out["weight_kg"] / (h_m * h_m)
    out["bmi"] = out["bmi"].where(out["bmi"].notna(), derived_bmi)
    if "bmi" in cfg.get("plausible_ranges", {}):
        lo, hi = map(float, cfg["plausible_ranges"]["bmi"])
        out["bmi"] = out["bmi"].where(out["bmi"].between(lo, hi))

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

    input_modes = []

    for p in files:
        df = read_table(p)
        integrated = split_integrated_wide(df, cfg)

        if integrated:
            input_modes.append("integrated_wide")
            wave_frames = integrated
        else:
            input_modes.append("one_wave_per_file")
            wave = detect_wave(p, cfg["wave_order"])
            wave_frames = [(wave, df)]

        for wave, wave_df in wave_frames:
            try:
                frame, resolved = build_wave_frame(wave_df, wave, cfg)
            except ValueError as exc:
                print(f"[SKIP] {p} [{wave}]: {exc}")
                continue

            frame["source_file"] = str(p)
            frame["source_mode"] = (
                "integrated_wide" if integrated else "one_wave_per_file"
            )
            frames.append(frame)

            for concept, col in resolved.items():
                mappings.append(
                    {
                        "wave": wave,
                        "source_file": str(p),
                        "source_mode": frame["source_mode"].iloc[0],
                        "concept": concept,
                        "resolved_column": col,
                    }
                )

    if not frames:
        raise SystemExit("No wave could be harmonized.")

    long = pd.concat(frames, ignore_index=True, sort=False)

    # Merge multiple controlled-data domain tables before any longitudinal
    # history, timing or age-anchor calculation so duplicate source tables do
    # not implicitly weight a participant-wave more than once.
    dup = long.duplicated(["person_id", "wave"], keep=False)
    dup_report = long.loc[
        dup,
        ["person_id", "wave", "source_file", "source_mode"],
    ].copy()
    write_table(dup_report, out / "DUPLICATE_PARTICIPANT_WAVE.tsv")

    long, conflict_report = coalesce_person_wave_rows(long)
    write_table(
        conflict_report,
        out / "DUPLICATE_PARTICIPANT_WAVE_CONFLICTS.tsv",
    )

    def mode_or_nan(s: pd.Series):
        x = s.dropna()
        return x.mode().iloc[0] if not x.empty else np.nan

    long["sex_male"] = long.groupby("person_id")["sex_male"].transform(mode_or_nan)

    long = long.sort_values(["person_id", "visit_index", "source_file"]).copy()
    for concept in cfg.get("binary_coding", {}).get("variables", []):
        if concept in long.columns and long[concept].notna().any():
            long[f"{concept}_history"] = (
                long.groupby("person_id", group_keys=False)[concept]
                .apply(cumulative_established_history)
                .reindex(long.index)
            )

    # Prefer actual examination dates for longitudinal time. Fall back to the
    # planned 2-year wave spacing only when dates are unavailable.
    base_dates = (
        long.loc[long["visit_index"].eq(0) & long["visit_date"].notna()]
        .groupby("person_id")["visit_date"]
        .min()
    )
    # Use a plain mapping for pandas 2.x/3.x compatibility with datetime values.
    long["baseline_visit_date"] = long["person_id"].map(base_dates.to_dict())
    actual_years = (
        (long["visit_date"] - long["baseline_visit_date"]).dt.total_seconds()
        / (365.25 * 24 * 60 * 60)
    )
    long["year_offset_source"] = np.where(
        actual_years.notna(), "actual_exam_date", "planned_wave"
    )
    long["year_offset"] = actual_years.fillna(long["year_offset_planned"])

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

    # Recompute cross-domain derived phenotypes after integrated tables have
    # been coalesced and sex/age are available at the participant-wave level.
    h_m = pd.to_numeric(long["height_cm"], errors="coerce") / 100.0
    derived_bmi = (
        pd.to_numeric(long["weight_kg"], errors="coerce")
        / (h_m * h_m)
    )
    long["bmi"] = pd.to_numeric(long["bmi"], errors="coerce").where(
        pd.to_numeric(long["bmi"], errors="coerce").notna(),
        derived_bmi,
    )
    if "bmi" in cfg.get("plausible_ranges", {}):
        lo, hi = map(float, cfg["plausible_ranges"]["bmi"])
        long["bmi"] = long["bmi"].where(long["bmi"].between(lo, hi))

    long["pulse_pressure"] = (
        pd.to_numeric(long["sbp"], errors="coerce")
        - pd.to_numeric(long["dbp"], errors="coerce")
    )
    long["non_hdl"] = (
        pd.to_numeric(long["total_cholesterol"], errors="coerce")
        - pd.to_numeric(long["hdl"], errors="coerce")
    )

    tg = pd.to_numeric(long["triglyceride"], errors="coerce")
    glu = pd.to_numeric(long["glucose"], errors="coerce")
    valid_tyg = tg.gt(0) & glu.gt(0)
    long["tyg"] = np.nan
    long.loc[valid_tyg, "tyg"] = np.log(
        tg.loc[valid_tyg] * glu.loc[valid_tyg] / 2.0
    )

    long["egfr_2021"] = egfr_2021(
        pd.to_numeric(long["creatinine"], errors="coerce"),
        pd.to_numeric(long["age"], errors="coerce"),
        pd.to_numeric(long["sex_male"], errors="coerce"),
    )
    long["nlr"] = (
        pd.to_numeric(long["neutrophil"], errors="coerce")
        / pd.to_numeric(long["lymphocyte"], errors="coerce").replace(0, np.nan)
    )
    long["fev1_fvc"] = (
        pd.to_numeric(long["fev1"], errors="coerce")
        / pd.to_numeric(long["fvc"], errors="coerce").replace(0, np.nan)
    )
    long = long.replace([np.inf, -np.inf], np.nan)

    # QC: measured age should be close to the wave-based subject anchor.
    expected_age = anchor + long["year_offset"]
    long["age_wave_residual_years"] = np.where(
        long["age_source"].eq("measured"),
        long["age"] - expected_age,
        np.nan,
    )

    long = long.sort_values(["person_id", "visit_index", "source_file"]).copy()

    write_table(pd.DataFrame(mappings), out / "RESOLVED_VARIABLE_MAP.tsv")

    dx_rows = []
    for concept in cfg.get("binary_coding", {}).get("variables", []):
        raw = f"{concept}_raw_code"
        hist = f"{concept}_history"
        if raw in long.columns:
            counts = long[raw].value_counts(dropna=False)
            for value, n in counts.items():
                dx_rows.append({
                    "concept": concept,
                    "raw_code": value,
                    "n_rows": int(n),
                })
        if hist in long.columns:
            base = long.loc[long["visit_index"].eq(0), hist]
            dx_rows.append({
                "concept": concept,
                "raw_code": "baseline_established_history_1",
                "n_rows": int(base.eq(1).sum()),
            })
    write_table(pd.DataFrame(dx_rows), out / "DIAGNOSIS_CODING_QC.tsv")

    write_table(long, out / "LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz")
    try:
        write_table(long, out / "LONGITUDINAL_MULTI_ORGAN_PANEL.parquet")
    except Exception as exc:
        print(f"[WARN] parquet write skipped: {exc}")

    visits = long.groupby("person_id")["wave"].nunique()
    age_resid = pd.to_numeric(long["age_wave_residual_years"], errors="coerce").dropna()

    qc_features = sorted(set(
        cfg.get("plausible_ranges", {}).keys()
        | set(cfg.get("concepts", {}).keys())
    ))
    missing_rows = []
    for c in qc_features:
        if c in long.columns:
            missing_rows.append({
                "feature": c,
                "n_nonmissing": int(long[c].notna().sum()),
                "n_missing": int(long[c].isna().sum()),
                "missing_fraction": float(long[c].isna().mean()),
            })
    write_table(pd.DataFrame(missing_rows), out / "FEATURE_MISSINGNESS_AFTER_QC.tsv")

    summary = {
        "rows": int(len(long)),
        "subjects": int(long["person_id"].nunique()),
        "waves": int(long["wave"].nunique()),
        "subjects_ge_3_visits": int((visits >= 3).sum()),
        "median_visits": float(visits.median()),
        "duplicate_rows_flagged": int(len(dup_report)),
        "duplicate_value_conflicts_flagged": int(len(conflict_report)),
        "input_modes": sorted(set(input_modes)),
        "integrated_wide_input_files": int(
            sum(mode == "integrated_wide" for mode in input_modes)
        ),
        "measured_age_rows": int(long["age_source"].eq("measured").sum()),
        "inferred_age_rows": int(long["age_source"].eq("inferred_from_subject_anchor").sum()),
        "median_abs_age_wave_residual_years": float(age_resid.abs().median()) if len(age_resid) else None,
        "rows_with_actual_exam_date_time": int(long["year_offset_source"].eq("actual_exam_date").sum()),
        "rows_with_planned_wave_time": int(long["year_offset_source"].eq("planned_wave").sum()),
        "median_followup_years_actual_or_fallback": float(
            pd.to_numeric(long["year_offset"], errors="coerce").median()
        ),
    }
    json_dump(summary, out / "STAGE1_SUMMARY.json")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
