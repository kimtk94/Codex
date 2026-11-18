from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from common import (
    detect_wave,
    ensure_dir,
    json_dump,
    list_input_files,
    load_config,
    norm_name,
    read_table,
    resolve_column,
    write_table,
)


WIDE_VISIT_RE = re.compile(r"^(a\d{1,2})_(.+)$", re.IGNORECASE)


def integrated_wave_columns(columns) -> dict[str, list[str]]:
    """Return A01/A02/... visit-prefixed columns for KoGES integrated wide files."""
    waves: dict[str, list[str]] = {}
    for original in columns:
        n = norm_name(original)
        m = WIDE_VISIT_RE.match(n)
        if m:
            waves.setdefault(m.group(1).lower(), []).append(original)
    return waves


def wave_sort_key(wave: str) -> tuple[int, str]:
    m = re.search(r"(\d+)", str(wave))
    return (int(m.group(1)) if m else 10**9, str(wave))


def derived_feature_waves(feature: str, availability_map: dict[str, int]) -> int:
    direct = int(availability_map.get(feature, 0))
    if direct:
        return direct

    if feature == "pulse_pressure":
        return min(
            int(availability_map.get("sbp", 0)),
            int(availability_map.get("dbp", 0)),
        )
    if feature == "tyg":
        return min(
            int(availability_map.get("glucose", 0)),
            int(availability_map.get("triglyceride", 0)),
        )
    if feature == "nlr":
        return min(
            int(availability_map.get("neutrophil", 0)),
            int(availability_map.get("lymphocyte", 0)),
        )
    if feature == "fev1_fvc":
        return max(
            int(availability_map.get("fev1_fvc_source", 0)),
            min(
                int(availability_map.get("fvc", 0)),
                int(availability_map.get("fev1", 0)),
            ),
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit controlled KoGES readiness for multi-organ aging analysis."
    )
    ap.add_argument("--config", required=True)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    input_dir = Path(
        args.input_dir
        or cfg["paths"].get(
            "controlled_input_dir",
            "/srv/is-analysis/data/multi_organ_aging/controlled",
        )
    )
    root = Path(args.out_dir or cfg["paths"]["out_dir"])
    out = ensure_dir(root / "stage0c_controlled_readiness")

    if not input_dir.exists():
        info = {
            "status": "not_available",
            "input_dir": str(input_dir),
            "reason": "controlled_input_dir_missing",
            "multi_organ_ready": False,
        }
        json_dump(info, out / "CONTROLLED_READINESS_SUMMARY.json")
        print(info)
        return 0

    files = list_input_files(input_dir, cfg["file_globs"])
    if not files:
        info = {
            "status": "not_available",
            "input_dir": str(input_dir),
            "reason": "no_supported_files_found",
            "multi_organ_ready": False,
        }
        json_dump(info, out / "CONTROLLED_READINESS_SUMMARY.json")
        print(info)
        return 0

    id_map = cfg["id_concepts"]
    concepts = cfg["concepts"]
    file_rows = []
    concept_rows = []
    id_wave_rows = []
    detected_waves: set[str] = set()

    for p in files:
        filename_wave = detect_wave(p, cfg["wave_order"])
        try:
            df = read_table(p)
        except Exception as exc:
            file_rows.append(
                {
                    "source_file": str(p),
                    "file_mode": "unreadable",
                    "wave": filename_wave,
                    "status": f"read_error:{type(exc).__name__}",
                    "rows": None,
                    "columns": None,
                }
            )
            continue

        wide = integrated_wave_columns(df.columns)
        is_integrated_wide = len(wide) >= 3

        global_person_col = resolve_column(df.columns, id_map["person_id"])

        if is_integrated_wide:
            mode = "integrated_wide"
            wave_items = sorted(wide.items(), key=lambda x: wave_sort_key(x[0]))

            person_candidates = [
                resolve_column(cols, id_map["person_id"])
                for _, cols in wave_items
            ]
            person_resolved = bool(
                global_person_col or any(x is not None for x in person_candidates)
            )

            age_hits = 0
            sex_hits = 0
            date_hits = 0

            for wave, cols in wave_items:
                detected_waves.add(wave)
                age_col = resolve_column(cols, id_map["age"])
                sex_col = resolve_column(cols, id_map["sex"])
                date_col = resolve_column(cols, id_map.get("visit_date", []))
                wave_person_col = resolve_column(cols, id_map["person_id"])

                age_hits += int(age_col is not None)
                sex_hits += int(sex_col is not None)
                date_hits += int(date_col is not None)

                id_wave_rows.append(
                    {
                        "source_file": str(p),
                        "wave": wave,
                        "person_id_column": global_person_col or wave_person_col,
                        "age_column": age_col,
                        "sex_column": sex_col,
                        "visit_date_column": date_col,
                        "person_id_resolved": bool(global_person_col or wave_person_col),
                        "age_resolved": bool(age_col),
                        "sex_resolved": bool(sex_col),
                        "visit_date_resolved": bool(date_col),
                    }
                )

                for concept, aliases in concepts.items():
                    col = resolve_column(cols, aliases)
                    concept_rows.append(
                        {
                            "source_file": str(p),
                            "file_mode": mode,
                            "wave": wave,
                            "concept": concept,
                            "resolved_column": col,
                            "resolved": bool(col),
                            "n_nonmissing": int(df[col].notna().sum()) if col else 0,
                        }
                    )

            file_rows.append(
                {
                    "source_file": str(p),
                    "file_mode": mode,
                    "wave": "integrated_wide",
                    "status": "ok",
                    "rows": int(len(df)),
                    "columns": int(len(df.columns)),
                    "detected_waves": len(wave_items),
                    "detected_wave_labels": ",".join(x[0] for x in wave_items),
                    "person_id_column": global_person_col,
                    "person_id_resolved": person_resolved,
                    "age_resolved": bool(age_hits >= 1),
                    "sex_resolved": bool(sex_hits >= 1),
                    "visit_date_resolved": bool(date_hits >= 1),
                    "age_waves_resolved": int(age_hits),
                    "sex_waves_resolved": int(sex_hits),
                    "visit_date_waves_resolved": int(date_hits),
                }
            )
            continue

        mode = "one_wave_per_file"
        detected_waves.add(filename_wave)

        person_col = global_person_col
        age_col = resolve_column(df.columns, id_map["age"])
        sex_col = resolve_column(df.columns, id_map["sex"])
        date_col = resolve_column(df.columns, id_map.get("visit_date", []))

        id_wave_rows.append(
            {
                "source_file": str(p),
                "wave": filename_wave,
                "person_id_column": person_col,
                "age_column": age_col,
                "sex_column": sex_col,
                "visit_date_column": date_col,
                "person_id_resolved": bool(person_col),
                "age_resolved": bool(age_col),
                "sex_resolved": bool(sex_col),
                "visit_date_resolved": bool(date_col),
            }
        )

        file_rows.append(
            {
                "source_file": str(p),
                "file_mode": mode,
                "wave": filename_wave,
                "status": "ok",
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "detected_waves": 1,
                "detected_wave_labels": filename_wave,
                "person_id_column": person_col,
                "age_column": age_col,
                "sex_column": sex_col,
                "visit_date_column": date_col,
                "person_id_resolved": bool(person_col),
                "age_resolved": bool(age_col),
                "sex_resolved": bool(sex_col),
                "visit_date_resolved": bool(date_col),
                "age_waves_resolved": int(bool(age_col)),
                "sex_waves_resolved": int(bool(sex_col)),
                "visit_date_waves_resolved": int(bool(date_col)),
            }
        )

        for concept, aliases in concepts.items():
            col = resolve_column(df.columns, aliases)
            concept_rows.append(
                {
                    "source_file": str(p),
                    "file_mode": mode,
                    "wave": filename_wave,
                    "concept": concept,
                    "resolved_column": col,
                    "resolved": bool(col),
                    "n_nonmissing": int(df[col].notna().sum()) if col else 0,
                }
            )

    file_df = pd.DataFrame(file_rows)
    concept_df = pd.DataFrame(concept_rows)
    id_wave_df = pd.DataFrame(id_wave_rows)

    write_table(file_df, out / "CONTROLLED_FILE_AUDIT.tsv")
    write_table(concept_df, out / "CONTROLLED_CONCEPT_AUDIT.tsv")
    write_table(id_wave_df, out / "CONTROLLED_ID_WAVE_AUDIT.tsv")

    ok_files = file_df[file_df["status"].eq("ok")].copy()
    n_waves = int(len(detected_waves))

    availability_rows = []
    if not concept_df.empty:
        for concept, g in concept_df.groupby("concept", sort=True):
            usable = g[g["resolved"] & g["n_nonmissing"].gt(0)]
            availability_rows.append(
                {
                    "concept": concept,
                    "waves_available": int(usable["wave"].nunique()),
                    "files_available": int(usable["source_file"].nunique()),
                    "total_nonmissing": int(usable["n_nonmissing"].sum()),
                    "repeated_3plus_waves": bool(usable["wave"].nunique() >= 3),
                    "wave_labels": ",".join(
                        sorted(
                            usable["wave"].astype(str).unique().tolist(),
                            key=wave_sort_key,
                        )
                    ),
                }
            )

    availability = pd.DataFrame(availability_rows)
    write_table(availability, out / "CONTROLLED_CONCEPT_AVAILABILITY.tsv")

    availability_map = (
        availability.set_index("concept")["waves_available"].to_dict()
        if not availability.empty
        else {}
    )

    organ_rows = []
    for organ, spec in cfg["organs"].items():
        features = list(spec["features"])
        min_features = int(spec["min_features"])

        wave_counts = {
            feature: derived_feature_waves(feature, availability_map)
            for feature in features
        }
        repeated = [
            f for f, n in wave_counts.items()
            if int(n) >= 3
        ]
        any_wave = [
            f for f, n in wave_counts.items()
            if int(n) >= 1
        ]

        ready = len(repeated) >= min_features and n_waves >= 3

        organ_rows.append(
            {
                "organ": organ,
                "configured_features": len(features),
                "min_features": min_features,
                "features_any_wave": len(any_wave),
                "features_repeated_3plus_waves": len(repeated),
                "repeated_features": ",".join(repeated),
                "organ_ready_for_pace": bool(ready),
            }
        )

    organ_df = pd.DataFrame(organ_rows)
    write_table(organ_df, out / "CONTROLLED_ORGAN_READINESS.tsv")

    ready_organs = organ_df.loc[
        organ_df["organ_ready_for_pace"], "organ"
    ].tolist()

    id_waves = (
        id_wave_df.groupby("wave").agg(
            person_id_resolved=("person_id_resolved", "max"),
            age_resolved=("age_resolved", "max"),
            sex_resolved=("sex_resolved", "max"),
            visit_date_resolved=("visit_date_resolved", "max"),
        )
        if not id_wave_df.empty
        else pd.DataFrame()
    )

    person_id_waves = (
        int(id_waves["person_id_resolved"].sum())
        if not id_waves.empty else 0
    )
    age_waves = (
        int(id_waves["age_resolved"].sum())
        if not id_waves.empty else 0
    )
    sex_waves = (
        int(id_waves["sex_resolved"].sum())
        if not id_waves.empty else 0
    )
    visit_date_waves = (
        int(id_waves["visit_date_resolved"].sum())
        if not id_waves.empty else 0
    )

    required_core = {
        "person_id_all_files": bool(
            not ok_files.empty
            and ok_files["person_id_resolved"].all()
        ),
        "person_id_waves_resolved": person_id_waves,
        "age_waves_resolved": age_waves,
        "sex_waves_resolved": sex_waves,
        "visit_date_waves_resolved": visit_date_waves,
        "age_3plus_waves": bool(age_waves >= 3),
        "visit_date_3plus_waves": bool(visit_date_waves >= 3),
    }

    outcome_waves = {
        concept: int(availability_map.get(concept, 0))
        for concept in ["htn_dx", "t2d_dx", "cvd_dx", "ckd_dx"]
    }

    go = (
        len(ready_organs) >= 3
        and required_core["person_id_all_files"]
        and required_core["age_3plus_waves"]
    )

    info = {
        "status": "ok",
        "input_dir": str(input_dir),
        "n_files": int(len(files)),
        "n_readable_files": int(len(ok_files)),
        "file_modes": (
            ok_files["file_mode"].value_counts().to_dict()
            if not ok_files.empty else {}
        ),
        "n_waves": n_waves,
        "wave_labels": sorted(detected_waves, key=wave_sort_key),
        "integrated_wide_detected": bool(
            not ok_files.empty
            and ok_files["file_mode"].eq("integrated_wide").any()
        ),
        "core_identifiers": required_core,
        "ready_organs": ready_organs,
        "n_ready_organs": int(len(ready_organs)),
        "multi_organ_ready": bool(len(ready_organs) >= 3),
        "preferred_four_organ_ready": bool(len(ready_organs) >= 4),
        "outcome_waves_available": outcome_waves,
        "go_no_go": "GO" if go else "HOLD",
        "note": (
            "Readiness is schema/availability QC only. Units, assay harmonization, "
            "diagnosis coding, repeated-measure definitions and event definitions "
            "still require manual verification."
        ),
    }

    json_dump(info, out / "CONTROLLED_READINESS_SUMMARY.json")
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
