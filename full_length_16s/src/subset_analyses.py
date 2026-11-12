#!/usr/bin/env python3
"""Recompute 16S plots and diversity for sample exclusion scenarios.

Do not claim DADA2 denoising was repeated: input is a single shared ASV table.
For an independent re-denoising sensitivity analysis use per-scenario manifests
generated with --manifest, then run QIIME 2 denoise-ccs per scenario.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from full16s import load_feature_table, report


VARIANTS = ("all", "no_controls", "no_three", "no_controls_no_three")


def load_three(path: Path | None, metadata: pd.DataFrame):
    if not path or not path.is_file():
        return None, "PENDING_THREE_SAMPLE_LIST"
    specs = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    if "sample-id" not in specs:
        raise ValueError("Three-sample exclusion TSV must have a 'sample-id' column")
    values = [x.strip() for x in specs["sample-id"].tolist() if x.strip()]
    if len(values) != 3 or len(set(values)) != 3:
        raise ValueError("Specify exactly three distinct, nonblank full sample-id values.")
    missing = set(values) - set(metadata["sample-id"])
    if missing:
        raise ValueError("The following exclusion IDs do not exist in metadata: " + ", ".join(sorted(missing)))
    return set(values), "READY"


def run_variants(feature_table, taxonomy, metadata_path, excluded_path, output_dir, manifest=None, selected=None):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    metadata = pd.read_csv(metadata_path, sep="\t", dtype=str).fillna("")
    if metadata["sample-id"].duplicated().any():
        raise ValueError("Metadata sample-id must be unique. Sample names PC/NC may repeat; Novogene IDs must not.")
    if "control" not in metadata:
        metadata["control"] = np.where(metadata["sample-name"].str.upper().isin(["PC", "NC"]),
                                       metadata["sample-name"].str.upper(), "NONE")
    controls = set(metadata.loc[metadata["control"].str.upper().isin(["PC", "NC"]), "sample-id"])
    excluded_three, three_status = load_three(Path(excluded_path) if excluded_path else None, metadata)
    raw = load_feature_table(feature_table)
    sample_columns = [x for x in raw.columns if x in set(metadata["sample-id"])]
    unmatched = sorted(set(raw.columns) - set(metadata["sample-id"]))
    if not sample_columns:
        raise ValueError("No ASV table columns overlap metadata sample-id")
    if unmatched:
        raise ValueError("ASV table sample IDs not found in metadata: " + ", ".join(unmatched[:10]))
    outputs = []
    base_reads = int(raw[sample_columns].sum().sum())
    man = pd.read_csv(manifest, sep="\t", dtype=str) if manifest else None
    if man is not None and (set(sample_columns) - set(man["sample-id"])):
        raise ValueError("Manifest lacks ASV table sample IDs")
    if selected is not None and selected not in VARIANTS:
        raise ValueError(f"Unknown scenario: {selected}")
    for scenario in ((selected,) if selected else VARIANTS):
        use_three = scenario in ("no_three", "no_controls_no_three")
        if use_three and excluded_three is None:
            outputs.append({"scenario": scenario, "status": "BLOCKED",
                            "reason": three_status, "n_samples": None})
            continue
        excluded = set()
        if scenario in ("no_controls", "no_controls_no_three"):
            excluded |= controls
        if use_three:
            excluded |= excluded_three
        keep = [x for x in sample_columns if x not in excluded]
        if not keep:
            raise ValueError(f"{scenario}: exclusion removes every sample")
        sample_table = raw.loc[:, keep].copy()
        sample_table = sample_table.loc[sample_table.sum(axis=1) > 0]
        current = out / scenario
        current.mkdir(exist_ok=True)
        # BIOM-like TSV with sample IDs in columns, ASVs in rows.
        ftable = current / "feature-table.tsv"
        sample_table.index.name = "#OTU ID"
        sample_table.to_csv(ftable, sep="\t")
        md = metadata[metadata["sample-id"].isin(keep)].copy()
        md.to_csv(current / "metadata.tsv", sep="\t", index=False)
        analysis = report(ftable, taxonomy, current / "metadata.tsv", current)
        excluded_rows = metadata.loc[metadata["sample-id"].isin(excluded)].copy()
        excluded_rows["reason"] = excluded_rows["sample-id"].map(
            lambda x: ("control" if x in controls else "") + ("+specified_three" if excluded_three and x in excluded_three else ""))
        excluded_rows.to_csv(current / "excluded_samples.tsv", sep="\t", index=False)
        if man is not None:
            man.loc[man["sample-id"].isin(keep)].to_csv(current / "manifest.tsv", sep="\t", index=False)
        stats = {"scenario": scenario, "status": "PASS", "n_samples": len(keep),
                 "n_excluded": int(len(set(sample_columns) & excluded)),
                 "controls_excluded": int(len(set(sample_columns) & excluded & controls)),
                 "specified_three_excluded": int(len(set(sample_columns) & excluded & (excluded_three or set()))),
                 "reads_after_ASV": int(sample_table.sum().sum()),
                 "reads_baseline": base_reads,
                 "asvs_present": len(sample_table),
                 "report": str(current / "report.html")}
        stats.update({f"report_{k}": v for k,v in analysis.items()})
        outputs.append(stats)
    pd.DataFrame(outputs).to_csv(out / "scenario_comparison.csv", index=False)
    (out / "scenario_summary.json").write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return outputs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feature-table", required=True)
    p.add_argument("--metadata", required=True)
    p.add_argument("--taxonomy", default=None)
    p.add_argument("--exclude-three", default=None)
    p.add_argument("--manifest", default=None)
    p.add_argument("--scenario", choices=VARIANTS, default=None, help="Run only one named subset; useful for independent Colab notebooks")
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    run_variants(a.feature_table, a.taxonomy, a.metadata, a.exclude_three, a.output_dir, a.manifest, a.scenario)


if __name__ == "__main__":
    main()
