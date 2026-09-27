from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import (
    detect_wave,
    ensure_dir,
    json_dump,
    list_input_files,
    load_config,
    read_table,
    resolve_column,
    write_table,
)


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

    for p in files:
        wave = detect_wave(p, cfg["wave_order"])
        try:
            df = read_table(p)
        except Exception as exc:
            file_rows.append(
                {
                    "source_file": str(p),
                    "wave": wave,
                    "status": f"read_error:{type(exc).__name__}",
                    "rows": None,
                    "columns": None,
                }
            )
            continue

        person_col = resolve_column(df.columns, id_map["person_id"])
        age_col = resolve_column(df.columns, id_map["age"])
        sex_col = resolve_column(df.columns, id_map["sex"])
        date_col = resolve_column(df.columns, id_map.get("visit_date", []))

        file_rows.append(
            {
                "source_file": str(p),
                "wave": wave,
                "status": "ok",
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
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

        for concept, aliases in concepts.items():
            col = resolve_column(df.columns, aliases)
            concept_rows.append(
                {
                    "source_file": str(p),
                    "wave": wave,
                    "concept": concept,
                    "resolved_column": col,
                    "resolved": bool(col),
                    "n_nonmissing": int(df[col].notna().sum()) if col else 0,
                }
            )

    file_df = pd.DataFrame(file_rows)
    concept_df = pd.DataFrame(concept_rows)

    write_table(file_df, out / "CONTROLLED_FILE_AUDIT.tsv")
    write_table(concept_df, out / "CONTROLLED_CONCEPT_AUDIT.tsv")

    ok_files = file_df[file_df["status"].eq("ok")].copy()
    n_waves = int(ok_files["wave"].nunique()) if not ok_files.empty else 0

    availability_rows = []
    for concept, g in concept_df.groupby("concept", sort=True):
        usable = g[g["resolved"] & g["n_nonmissing"].gt(0)]
        availability_rows.append(
            {
                "concept": concept,
                "waves_available": int(usable["wave"].nunique()),
                "files_available": int(len(usable)),
                "total_nonmissing": int(usable["n_nonmissing"].sum()),
                "repeated_3plus_waves": bool(usable["wave"].nunique() >= 3),
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

        repeated = [
            f for f in features
            if int(availability_map.get(f, 0)) >= 3
        ]
        any_wave = [
            f for f in features
            if int(availability_map.get(f, 0)) >= 1
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

    required_core = {
        "person_id_all_files": bool(
            not ok_files.empty
            and ok_files["person_id_resolved"].all()
        ),
        "age_all_files": bool(
            not ok_files.empty
            and ok_files["age_resolved"].all()
        ),
        "visit_date_all_files": bool(
            not ok_files.empty
            and ok_files["visit_date_resolved"].all()
        ),
    }

    outcome_waves = {
        concept: int(availability_map.get(concept, 0))
        for concept in ["htn_dx", "t2d_dx", "cvd_dx", "ckd_dx"]
    }

    info = {
        "status": "ok",
        "input_dir": str(input_dir),
        "n_files": int(len(files)),
        "n_readable_files": int(len(ok_files)),
        "n_waves": n_waves,
        "core_identifiers": required_core,
        "ready_organs": ready_organs,
        "n_ready_organs": int(len(ready_organs)),
        "multi_organ_ready": bool(len(ready_organs) >= 3),
        "preferred_four_organ_ready": bool(len(ready_organs) >= 4),
        "outcome_waves_available": outcome_waves,
        "go_no_go": (
            "GO"
            if len(ready_organs) >= 3
            and required_core["person_id_all_files"]
            and required_core["age_all_files"]
            else "HOLD"
        ),
        "note": (
            "Readiness is schema/availability QC only. Units, assay harmonization, "
            "diagnosis coding and event definitions still require manual verification."
        ),
    }

    json_dump(info, out / "CONTROLLED_READINESS_SUMMARY.json")
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
