#!/usr/bin/env python3
"""Prepare only approved PacBio HiFi FASTQs from ZIP or a local folder.

Uses the exact 90/87/16 sample manifest. PC, NC, and the selected P92 flagged
samples cannot leak into FASTQ extraction or DADA2 ASV inference.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import re
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

from full16s import FASTQ_RE, manifest, read_tsv, write_tsv
from project_splits import PROJECTS, THREE_EXCLUDED_FKDN, validate_and_split


def included_metadata(full_metadata, project, scenario):
    if project not in PROJECTS or scenario not in PROJECTS[project]["allowed_scenarios"]:
        raise ValueError(f"Only PC/NC-free scenarios are allowed: {project}/{scenario}")
    df = validate_and_split(full_metadata)[project]
    df = df.loc[~df["control"].str.upper().isin(["PC", "NC"])].copy()
    if scenario == "no_controls_no_three":
        df = df.loc[~df["novogene-id"].isin(THREE_EXCLUDED_FKDN)].copy()
    expected = {("P92", "no_controls"): 90, ("P92", "no_controls_no_three"):87,
                ("P18", "no_controls"):16}[(project, scenario)]
    if len(df) != expected:
        raise ValueError(f"{project}/{scenario}: expected {expected}, got {len(df)}")
    return df


def classify(name, metadata):
    name = name.replace("\\", "/")
    by_id = [row for row in metadata if row["novogene-id"].lower() in name.lower()]
    if len(by_id) == 1:
        return by_id[0]
    if len(by_id) > 1:
        raise ValueError("Ambiguous Novogene IDs in FASTQ path: " + name)
    # Explicit token boundaries prevent e.g. KCT_W1_01 matching KCT_W1_010
    aliases = ("sample-name", "report-name", "sample-id")
    matches = []
    for row in metadata:
        tokens = [row.get(col, "") for col in aliases]
        if any(token and re.search(r"(?<![A-Za-z0-9])" + re.escape(token) +
                                   r"(?![A-Za-z0-9])", name, re.I)
               for token in tokens):
            matches.append(row)
    if len(matches) > 1:
        raise ValueError("Ambiguous FASTQ sample path: " + name)
    return matches[0] if matches else None


def _safe_name(row, index, extension):
    return f"{row['sample-id']}__lane{index:04d}{extension}"


def prepare_from_zip(zip_path, metadata, dest):
    metadata = list(metadata)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    counter = defaultdict(int)
    extracted = []
    with zipfile.ZipFile(zip_path) as z:
        all_fastq = [entry for entry in z.infolist()
                     if not entry.is_dir() and FASTQ_RE.search(entry.filename)]
        if not all_fastq:
            raise ValueError("ZIP archive contains no .fastq/.fq(.gz) files. "
                             "It cannot be used for FASTQ-only denoising.")
        for entry in all_fastq:
            row = classify(entry.filename, metadata)
            if not row:  # Another project, PC/NC, or an explicitly excluded sample.
                continue
            counter[row["sample-id"]] += 1
            suffix = ".fastq.gz" if entry.filename.lower().endswith(".gz") else ".fastq"
            new_path = dest / _safe_name(row, counter[row["sample-id"]], suffix)
            if new_path.exists() and new_path.stat().st_size == entry.file_size:
                pass
            else:
                with z.open(entry) as source, new_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
            extracted.append({"sample-id": row["sample-id"],
                              "source": entry.filename,
                              "prepared_path": str(new_path.resolve()),
                              "bytes": entry.file_size})
    if not extracted:
        raise ValueError("Archive contains FASTQ, but none match the selected project sample IDs")
    return extracted


def prepare_from_directory(source_dir, metadata, dest):
    metadata = list(metadata)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    counter = defaultdict(int)
    extracted = []
    for src in sorted(Path(source_dir).rglob("*")):
        if not src.is_file() or not FASTQ_RE.search(src.name):
            continue
        row = classify(str(src.relative_to(source_dir)), metadata)
        if not row:
            continue
        counter[row["sample-id"]] += 1
        suffix = ".fastq.gz" if src.name.lower().endswith(".gz") else ".fastq"
        dst = dest / _safe_name(row, counter[row["sample-id"]], suffix)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        extracted.append({"sample-id": row["sample-id"],
                          "source": str(src),
                          "prepared_path": str(dst.resolve()),
                          "bytes": src.stat().st_size})
    if not extracted:
        raise FileNotFoundError("No matching sample FASTQ files in directory")
    return extracted


def run(metadata_path, project, scenario, output, zip_path=None, directory=None):
    if (zip_path is None) == (directory is None):
        raise ValueError("Provide exactly one of --zip or --directory")
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    subset = included_metadata(metadata_path, project, scenario)
    subset_meta = out / "analysis_metadata.tsv"
    subset.to_csv(subset_meta, sep="\t", index=False)
    rows = subset.to_dict("records")
    fastq_dir = out / "FASTQ"
    entries = (prepare_from_zip(zip_path, rows, fastq_dir) if zip_path
               else prepare_from_directory(directory, rows, fastq_dir))
    inventory = out / "fastq_inventory.tsv"
    write_tsv(inventory, entries, ["sample-id","source","prepared_path","bytes"])
    target = out / "manifest.tsv"
    manifest(fastq_dir, subset_meta, target, out/"merged_lanes")
    actual = read_tsv(target)
    actual_ids = {x["sample-id"] for x in actual}
    wanted_ids = set(subset["sample-id"])
    if actual_ids != wanted_ids:
        missing = sorted(wanted_ids - actual_ids)
        unexpected = sorted(actual_ids - wanted_ids)
        raise ValueError(f"Expected all {len(wanted_ids)} samples but FASTQ import is incomplete. "
                         f"Missing: {missing[:20]}, unexpected: {unexpected[:20]}")
    if any("PC__" in x or "NC__" in x for x in actual_ids):
        raise ValueError("Safety violation: PC/NC appeared in FASTQ manifest")
    audit = {"project":project, "scenario":scenario, "expected_samples":len(wanted_ids),
             "manifest_samples":len(actual), "fastq_sources":len(entries),
             "excluded_controls":2,
             "excluded_three":3 if scenario == "no_controls_no_three" else 0,
             "status":"PASS", "manifest":str(target)}
    (out/"manifest_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    return audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metadata",required=True)
    p.add_argument("--project",choices=tuple(PROJECTS),required=True)
    p.add_argument("--scenario",choices=("no_controls","no_controls_no_three"),required=True)
    p.add_argument("--output",required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--zip")
    group.add_argument("--directory")
    x=p.parse_args()
    run(x.metadata,x.project,x.scenario,x.output,x.zip,x.directory)


if __name__=="__main__":
    main()
