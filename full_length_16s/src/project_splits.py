#!/usr/bin/env python3
"""Strict 92/18 KIST split based on Excel order; generate independent reports.

P92: Excel sample rows 1..92 inclusive, KCT/K902/K905 and their PC/NC.
P18: Excel sample rows 93..110, KUW/KUD/KCR/KDR and their PC/NC.
Exclusion of three specific flagged samples applies ONLY to P92.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from full16s import load_feature_table, write_tsv
from subset_analyses import run_variants

PROJECTS = {
    "P92": {
        "start": 0, "stop": 92, "n": 92,
        "first": ("KCT_W1_01", "FKDN260619013-1A"),
        "last": ("NC", "FKDN260619104-1A"),
        "controls": {"PC": "FKDN260619103-1A", "NC": "FKDN260619104-1A"},
        "allowed_scenarios": ("all", "no_controls", "no_controls_no_three"),
    },
    "P18": {
        "start": 92, "stop": 110, "n": 18,
        "first": ("KUW_01", "FKDN260618712-1A"),
        "last": ("NC", "FKDN260618729-1A"),
        "controls": {"PC": "FKDN260618728-1A", "NC": "FKDN260618729-1A"},
        "allowed_scenarios": ("all", "no_controls"),
    },
}

THREE_EXCLUDED_FKDN = (
    "FKDN260619042-1A",  # K905_W1_10
    "FKDN260619082-1A",  # KCT_W3_10
    "FKDN260619084-1A",  # K902_W3_02
)


def validate_and_split(metadata_path: str | Path) -> dict[str, pd.DataFrame]:
    metadata = pd.read_csv(metadata_path, sep="\t", dtype=str).fillna("")
    for col in ("sample-id", "sample-name", "novogene-id", "control"):
        if col not in metadata:
            raise ValueError(f"Metadata missing required column: {col}")
    if len(metadata) != 110:
        raise ValueError(f"Expected exactly 110 sample rows (92+18), found {len(metadata)}")
    if metadata["novogene-id"].duplicated().any() or metadata["sample-id"].duplicated().any():
        raise ValueError("Duplicate unique FKDN ID or sample-id in metadata")
    result = {}
    for project, rule in PROJECTS.items():
        segment = metadata.iloc[rule["start"]:rule["stop"]].copy()
        if len(segment) != rule["n"]:
            raise ValueError(f"{project}: incorrect segment length")
        for position, expected in ((0, rule["first"]), (-1, rule["last"])):
            actual = (segment.iloc[position]["sample-name"], segment.iloc[position]["novogene-id"])
            if actual != expected:
                raise ValueError(f"{project}: wrong Excel order at boundary {position}: {actual}, expected {expected}")
        controls = segment.loc[segment["control"].str.upper().isin(["PC","NC"])]
        if len(controls) != 2:
            raise ValueError(f"{project}: expected exactly one PC and one NC; got {len(controls)}")
        actual_control_ids = dict(zip(controls["control"], controls["novogene-id"]))
        if actual_control_ids != rule["controls"]:
            raise ValueError(f"{project}: control IDs mismatch: {actual_control_ids}")
        segment["project"] = project
        segment["excel_order"] = range(rule["start"] + 1, rule["stop"] + 1)
        result[project] = segment
    p92_ids = set(result["P92"]["novogene-id"])
    if not set(THREE_EXCLUDED_FKDN).issubset(p92_ids):
        raise ValueError("The three requested exclusions must all belong to the upper 92 project")
    if set(result["P92"]["novogene-id"]) & set(result["P18"]["novogene-id"]):
        raise ValueError("Cross-project FKDN collision")
    return result


def save_metadata(metadata_path, project, output):
    scoped = validate_and_split(metadata_path)[project]
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    scoped.to_csv(out, sep="\t", index=False)
    return scoped


def _normalize_columns(full_table: pd.DataFrame, scoped: pd.DataFrame, other: pd.DataFrame, project: str):
    own_ids = set(scoped["sample-id"])
    others = set(other["sample-id"])
    own_names = set(scoped["sample-name"])
    other_names = set(other["sample-name"])
    own_fkdn = set(scoped["novogene-id"])
    other_fkdn = set(other["novogene-id"])
    observed = {str(x) for x in full_table.columns}
    # If the ASV table contains samples from both projects, duplicated PC / NC
    # cannot be assigned safely by bare sample name; require full ID / FKDN.
    mixed = bool(observed & (others | other_fkdn | (other_names - own_names)))
    if mixed and (observed & {"PC", "NC"}):
        raise ValueError("Mixed-project feature table has ambiguous bare PC/NC labels. "
                         "Provide full sample-id or FKDN IDs for BOTH controls in the input table.")
    by_full = {r["sample-id"]:r["sample-id"] for _,r in scoped.iterrows()}
    by_fkdn = {r["novogene-id"]:r["sample-id"] for _,r in scoped.iterrows()}
    counts = Counter(scoped["sample-name"])
    by_name = {r["sample-name"]:r["sample-id"] for _,r in scoped.iterrows()
               if counts[r["sample-name"]] == 1}
    selection = {}
    for col in full_table.columns:
        label = str(col)
        name = by_full.get(label) or by_fkdn.get(label) or by_name.get(label)
        if name:
            if name in selection.values():
                raise ValueError(f"Two input feature-table columns refer to same sample-id: {name}")
            selection[col] = name
    selected = full_table.loc[:,list(selection)].copy()
    selected.rename(columns=selection, inplace=True)
    missing = sorted(own_ids - set(selected.columns))
    if missing:
        raise ValueError(f"{project}: ASV table missing {len(missing)}/{len(scoped)} required samples "
                         f"(including controls): {missing[:8]}. The report is BLOCKED rather "
                         "than incorrectly treating absent samples as zeros.")
    return selected.loc[:,scoped["sample-id"].tolist()]


def prepare(feature_table, metadata_path, project, output_dir):
    if project not in PROJECTS:
        raise ValueError(f"Unknown project {project}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    project_map = validate_and_split(metadata_path)
    scoped = project_map[project]
    scoped.to_csv(out / "metadata.tsv", sep="\t", index=False)
    full_table = load_feature_table(feature_table)
    other_id = "P18" if project == "P92" else "P92"
    selected = _normalize_columns(full_table, scoped, project_map[other_id], project)
    selected.index.name = "#OTU ID"
    selected.to_csv(out / "feature-table.tsv", sep="\t")
    x3 = scoped.loc[scoped["novogene-id"].isin(THREE_EXCLUDED_FKDN), ["sample-id", "sample-name", "novogene-id"]]
    if project == "P92":
        if len(x3) != 3:
            raise ValueError("P92 must contain all three user-specified exclusion IDs")
        x3.to_csv(out / "exclude_three_samples.tsv", sep="\t", index=False)
    return {
        "project": project,
        "metadata": out/"metadata.tsv",
        "table": out/"feature-table.tsv",
        "exclude": out/"exclude_three_samples.tsv" if project=="P92" else None,
        "n_samples": len(scoped),
        "controls": int(scoped["control"].isin(["PC","NC"]).sum()),
    }


def run(feature_table, metadata_path, project, scenario, output_dir, taxonomy=None):
    if scenario not in PROJECTS[project]["allowed_scenarios"]:
        raise ValueError(f"{scenario} is not a valid scenario for {project}")
    out = Path(output_dir)
    inputs = prepare(feature_table, metadata_path, project, out/"project_input")
    outputs = run_variants(inputs["table"], taxonomy, inputs["metadata"], inputs["exclude"],
                           out/"reports", selected=scenario)
    result = outputs[0]
    expected = {"P92":{"all":92,"no_controls":90,"no_controls_no_three":87},
                "P18":{"all":18,"no_controls":16}}[project][scenario]
    if result["status"] != "PASS" or result["n_samples"] != expected:
        raise ValueError(f"{project}/{scenario}: expected {expected} samples; actual: {result}")
    manifest = {"project":project, "scenario":scenario, "expected_samples":expected,
                "actual_samples":result["n_samples"], "controls":inputs["controls"],
                "excluded_three_fkdn":list(THREE_EXCLUDED_FKDN) if scenario=="no_controls_no_three" else [],
                "run_type":"shared_ASV_table_then_subset_diversity",
                "status":"PASS"}
    (out/"project_run.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(manifest,indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd",required=True)
    s = sub.add_parser("split")
    s.add_argument("--metadata",required=True)
    s.add_argument("--output-dir",required=True)
    s = sub.add_parser("run")
    s.add_argument("--metadata",required=True)
    s.add_argument("--feature-table",required=True)
    s.add_argument("--taxonomy",default=None)
    s.add_argument("--project",choices=PROJECTS,required=True)
    s.add_argument("--scenario",required=True)
    s.add_argument("--output-dir",required=True)
    args = parser.parse_args()
    if args.cmd == "split":
        p = Path(args.output_dir)
        p.mkdir(parents=True,exist_ok=True)
        results = validate_and_split(args.metadata)
        for project, df in results.items():
            df.to_csv(p/(project+"_metadata.tsv"),sep="\t",index=False)
            print(project, len(df), "controls", df["control"].value_counts().to_dict())
    else:
        run(args.feature_table,args.metadata,args.project,args.scenario,
            args.output_dir,args.taxonomy)


if __name__ == "__main__":
    main()
