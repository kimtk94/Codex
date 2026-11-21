#!/usr/bin/env python3
"""Produce validated F003-90 and F003-87 diversity reports from local DADA2 ASVs.

F003-87 is a SUBSET of F003-90 inferred ASVs, not independent DADA2 denoising.
Does not change original raw data or running DADA2 process.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

EXCLUDED_87 = {"K905_W1_10", "KCT_W3_10", "K902_W3_02"}
EXPECTED_90 = 90
EXPECTED_87 = 87


def produce(root: Path, table_path: Path | None = None, metadata_path: Path | None = None) -> dict:
    import pandas as pd

    root = root.resolve()
    code = root / "code"
    sys.path.insert(0, str(code))
    from full16s import report  # project-tested diversity, Bray-Curtis and PCoA logic

    table_path = table_path or root / "F003_90" / "DADA2" / "feature-table.tsv"
    metadata_path = metadata_path or root / "metadata" / "projects" / "P92_metadata.tsv"
    if not table_path.is_file():
        raise FileNotFoundError(f"DADA2 ASV feature table not produced yet: {table_path}")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Project metadata missing: {metadata_path}")
    raw = pd.read_csv(table_path, sep="\t")
    meta = pd.read_csv(metadata_path, sep="\t")
    if raw.empty or "ASV_ID" not in raw.columns:
        raise ValueError("Expected non-empty ASV table with ASV_ID as the first column")
    if raw["ASV_ID"].duplicated().any():
        raise ValueError("Duplicate ASV IDs")
    for key in ("sample-id", "sample-name"):
        if key not in meta:
            raise ValueError(f"Missing metadata field {key}")
    if meta["sample-id"].duplicated().any():
        raise ValueError("Duplicate sample-id in metadata")
    cols = list(raw.columns[1:])
    if len(cols) != EXPECTED_90 or len(set(cols)) != EXPECTED_90:
        raise ValueError(f"Expected exactly 90 distinct biological samples, got {len(cols)}")
    if not set(cols).issubset(set(meta["sample-id"])):
        raise ValueError("Sample IDs in ASV table are not all present in F003 metadata")
    selected = meta[meta["sample-id"].isin(cols)].copy()
    if len(selected) != EXPECTED_90:
        raise ValueError(f"Metadata should match 90 biological samples, got {len(selected)}")
    if set(selected["sample-name"]).intersection({"PC", "NC"}):
        raise ValueError("PC/NC unexpectedly present in ASV table")
    if selected["sample-name"].duplicated().any():
        raise ValueError("Duplicated biological sample names")
    exclusion_ids = set(selected.loc[selected["sample-name"].isin(EXCLUDED_87), "sample-id"])
    if len(exclusion_ids) != 3:
        raise ValueError(f"F003 87 required exclusions not found exactly: {len(exclusion_ids)}")
    cols87 = [x for x in cols if x not in exclusion_ids]
    if len(cols87) != EXPECTED_87:
        raise ValueError(f"Expected 87 samples, got {len(cols87)}")

    count = raw.iloc[:, 1:].apply(pd.to_numeric, errors="raise")
    if count.isna().any().any() or (count < 0).any().any():
        raise ValueError("ASV counts contain negative or missing values")
    if not ((count % 1) == 0).all().all():
        raise ValueError("ASV counts must be integers")
    total90 = int(count.to_numpy().sum())
    total87 = int(count[cols87].to_numpy().sum())

    dest = root / "F003_90"
    summary = {}
    for scenario, keep in (("F003_90", cols), ("F003_87", cols87)):
        out = dest / f"reports_{scenario}"
        out.mkdir(parents=True, exist_ok=True)
        smeta = selected.loc[selected["sample-id"].isin(keep)]
        if len(smeta) != len(keep):
            raise ValueError(f"Metadata mismatch in scenario: {scenario}")
        metaout = out / "metadata.tsv"
        smeta.to_csv(metaout, sep="\t", index=False)
        tabout = out / "feature-table.tsv"
        raw.loc[:, ["ASV_ID", *keep]].to_csv(tabout, sep="\t", index=False)
        report(tabout, None, metaout, out)
        info = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        expected = len(keep)
        if info["samples_analyzed"] != expected:
            raise ValueError(f"{scenario} sample count mismatch {info}")
        if info["reads_after_denoising"] != (total90 if scenario == "F003_90" else total87):
            raise ValueError(f"{scenario} ASV read counts mismatch {info}")
        for fname in ("alpha_diversity.csv", "bray_curtis.csv",
                      "pcoa.csv", "pcoa_bray_curtis.png", "alpha_richness.png"):
            if not (out / fname).is_file():
                raise FileNotFoundError(f"{scenario}: missing {fname}")
        summary[scenario] = {"samples": expected,
                             "total_asvs": int(info["total_asvs"]),
                             "asv_reads": int(info["reads_after_denoising"]),
                             "report": str(out)}

    summary["F003_87"]["excluded_samples"] = sorted(EXCLUDED_87)
    summary["F003_87"]["interpretation"] = (
        "Subset of the F003_90 ASV table; not independent DADA2 denoising"
    )
    summary["taxonomy"] = "NOT RUN (no SILVA classifier)"
    (dest / "reports_validation.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORTS_PASS", json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
        default=Path.home() / "Documents" / "KIST16S_Local")
    parser.add_argument("--table", type=Path, default=None)
    parser.add_argument("--metadata", type=Path, default=None)
    args = parser.parse_args()
    produce(args.root, args.table, args.metadata)
