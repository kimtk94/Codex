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
    resolve_concepts,
    sha256_file,
    write_table,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit KoGES/public files for multi-organ aging feasibility.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    input_dir = Path(args.input_dir or cfg["paths"]["input_dir"])
    out_root = Path(args.out_dir or cfg["paths"]["out_dir"])
    out = ensure_dir(out_root / "stage0_audit")

    files = list_input_files(input_dir, cfg["file_globs"])
    if not files:
        raise SystemExit(f"No input files found under {input_dir}")

    id_aliases = cfg["id_concepts"]
    concept_aliases = cfg["concepts"]
    all_aliases = {**id_aliases, **concept_aliases}

    manifest_rows = []
    coverage_rows = []

    for p in files:
        df = read_table(p, nrows=50)
        wave = detect_wave(p, cfg["wave_order"])
        resolved = resolve_concepts(df.columns, all_aliases)
        manifest_rows.append(
            {
                "wave": wave,
                "file": str(p),
                "n_columns": len(df.columns),
                "sha256": sha256_file(p),
            }
        )
        for concept, col in resolved.items():
            coverage_rows.append(
                {
                    "wave": wave,
                    "file": str(p),
                    "concept": concept,
                    "resolved_column": col,
                    "present": int(col is not None),
                }
            )

    manifest = pd.DataFrame(manifest_rows).sort_values(["wave", "file"])
    coverage = pd.DataFrame(coverage_rows)
    write_table(manifest, out / "WAVE_FILE_MANIFEST.tsv")
    write_table(coverage, out / "VARIABLE_COVERAGE.tsv")

    wide = coverage.pivot_table(
        index="wave", columns="concept", values="present", aggfunc="max", fill_value=0
    )

    if {"sbp", "dbp"}.issubset(wide.columns):
        wide["pulse_pressure"] = ((wide["sbp"] > 0) & (wide["dbp"] > 0)).astype(int)
    if {"triglyceride", "glucose"}.issubset(wide.columns):
        wide["tyg"] = ((wide["triglyceride"] > 0) & (wide["glucose"] > 0)).astype(int)
    if {"creatinine", "age", "sex"}.issubset(wide.columns):
        wide["egfr_2021"] = (
            (wide["creatinine"] > 0) & (wide["age"] > 0) & (wide["sex"] > 0)
        ).astype(int)
    if {"neutrophil", "lymphocyte"}.issubset(wide.columns):
        wide["nlr"] = ((wide["neutrophil"] > 0) & (wide["lymphocyte"] > 0)).astype(int)
    if {"fev1", "fvc"}.issubset(wide.columns):
        wide["fev1_fvc"] = ((wide["fev1"] > 0) & (wide["fvc"] > 0)).astype(int)

    feasibility = []
    for organ, spec in cfg["organs"].items():
        feats = spec["features"]
        available = [f for f in feats if f in wide.columns]
        per_wave = wide[available].sum(axis=1) if available else pd.Series(0, index=wide.index)
        min_features = int(spec["min_features"])
        usable_waves = per_wave[per_wave >= min_features]
        feasibility.append(
            {
                "organ": organ,
                "configured_features": len(feats),
                "features_seen_any_wave": len(available),
                "min_features_required": min_features,
                "n_usable_waves": int(len(usable_waves)),
                "usable_waves": ",".join(map(str, usable_waves.index.tolist())),
                "max_features_in_wave": int(per_wave.max()) if len(per_wave) else 0,
                "feasible_for_longitudinal": int(len(usable_waves) >= 3),
            }
        )
    feasibility_df = pd.DataFrame(feasibility)
    write_table(feasibility_df, out / "ORGAN_FEASIBILITY.tsv")

    summary = {
        "input_dir": str(input_dir),
        "n_files": len(files),
        "waves": sorted(manifest["wave"].astype(str).unique().tolist()),
        "n_waves": int(manifest["wave"].nunique()),
        "feasible_organs": feasibility_df.loc[
            feasibility_df["feasible_for_longitudinal"].eq(1), "organ"
        ].tolist(),
        "note": "Stage 0 is schema discovery only. Exact KoGES variable mapping must be manually verified before inferential analysis.",
    }
    json_dump(summary, out / "STAGE0_SUMMARY.json")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
