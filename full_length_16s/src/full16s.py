#!/usr/bin/env python3
"""Full-length 16S: KIST sample mapping, FASTQ manifest, ZIP audit and report."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import html
import json
import math
import re
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

ID_RE = re.compile(r"FKDN\d{9}-\d+[A-Z]", re.I)
FASTQ_RE = re.compile(r"\.(fastq|fq)(\.gz)?$", re.I)
RANKS = ["Domain", "Phylum", "Class", "Order", "Family", "Genus", "Species"]


def write_tsv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_tsv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def infer_group(name):
    x = re.fullmatch(r"(KCT|K902|K905)_W(\d+)_(\d+)", name, re.I)
    if x:
        return x.group(1).upper(), "W" + x.group(2)
    x = re.fullmatch(r"(KUW|KUD|KCR|KDR)_(\d+)", name, re.I)
    if x:
        return x.group(1).upper(), "NA"
    if name.upper() in {"PC", "NC"}:
        return "CONTROL", "NA"
    return "UNSPECIFIED", "NA"


def report_labels(name, fid):
    """Fallback mapping verified against the Nov 12 KIST spreadsheet upload."""
    match = re.fullmatch(r"(KCT|K902|K905)_W([1-3])_(\d{2})", name)
    if match:
        prefix = {"KCT": "CT", "K902": "M902", "K905": "M905"}[match.group(1)]
        return f"{prefix}.W{match.group(2)}.{match.group(3)}", f"{prefix}.W{match.group(2)}"
    match = re.fullmatch(r"(KUW|KUD|KCR|KDR)_(\d{2})", name)
    if match:
        prefix, group = {
            "KUW": ("Blank.W", "Blank.W"), "KUD": ("Blank.D", "Blank.D"),
            "KCR": ("CT", "Control"), "KDR": ("TR", "Drought")
        }[match.group(1)]
        return f"{prefix}.{match.group(2)}", group
    if name in {"PC", "NC"}:
        tail = "Motion" if fid in {"FKDN260619103-1A", "FKDN260619104-1A"} else "Drought"
        return f"{name}.{tail}", ""
    return name, ""


def samples(xlsx, output):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    pairs = []
    seen = set()
    for ws in wb.worksheets:
        for cells in ws.iter_rows(values_only=True):
            arr = [str(x).strip() if x is not None else "" for x in cells]
            for i, value in enumerate(arr):
                if not ID_RE.fullmatch(value):
                    continue
                name = arr[i-1] if i else ""
                if not name or name.lower().startswith(("sample", "novogene")):
                    continue
                if value in seen:
                    continue
                seen.add(value)
                cohort, week = infer_group(name)
                inferred_report, inferred_group = report_labels(name, value)
                excel_report = arr[i+1] if i+1 < len(arr) else ""
                excel_group = arr[i+2] if i+2 < len(arr) else ""
                # Preserve the uploaded workbook naming scheme even when the
                # older Drive copy has not yet been updated.
                report_name = excel_report or inferred_report
                group_name = excel_group or inferred_group
                if excel_report and excel_report != inferred_report:
                    raise ValueError(f"Unexpected report name for {value}: {excel_report} != {inferred_report}")
                if excel_group and excel_group != inferred_group:
                    raise ValueError(f"Unexpected analysis group for {value}: {excel_group} != {inferred_group}")
                pairs.append({"sample-id": name + "__" + value, "sample-name": name,
                              "novogene-id": value, "report-name": report_name,
                              "group-name": group_name, "cohort": cohort, "week": week,
                              "control": name.upper() if name.upper() in ("PC", "NC") else "NONE"})
    if not pairs:
        raise ValueError("No Novogene FKDN sample IDs discovered in workbook")
    if len(pairs) != 110:
        raise ValueError(f"Expected 110 KIST sample entries, found {len(pairs)}")
    write_tsv(output, pairs, list(pairs[0]))
    print(json.dumps({"samples": len(pairs), "unique_novogene_ids": len(seen),
                      "controls": sum(x["control"] != "NONE" for x in pairs),
                      "output": str(output)}, ensure_ascii=False))
    return pairs


def inspect_zip(path, output):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        types = defaultdict(int)
        for name in names:
            low = name.lower()
            if FASTQ_RE.search(low):
                key = "fastq"
            elif low.endswith(".qza"):
                key = "qiime_qza"
            elif low.endswith((".tsv", ".csv", ".txt")):
                key = "tabular"
            elif low.endswith((".html", ".qzv", ".pdf")):
                key = "report"
            else:
                key = "other"
            types[key] += 1
        summary = {"archive": Path(path).name, "entries": len(names),
                   "types": dict(types),
                   "selected_entries": [x for x in names if
                       FASTQ_RE.search(x) or x.lower().endswith(
                           (".qza", "feature-table.tsv", "taxonomy.tsv", "metadata.tsv"))][:1000]}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "selected_entries"}, ensure_ascii=False))
    return summary


def manifest(fastq_dir, metadata, output, prepare_dir):
    files = sorted(p for p in Path(fastq_dir).rglob("*") if p.is_file() and FASTQ_RE.search(p.name))
    if not files:
        raise FileNotFoundError("No FASTQ files found; the existing result ZIP is not assumed to contain raw reads")
    mapping = read_tsv(metadata)
    assigned = defaultdict(list)
    unknown = []
    for p in files:
        # Prefer explicit Novogene IDs; filename detection must not silently assign ambiguous names.
        matches = [m for m in mapping if m["novogene-id"] in p.name]
        if not matches:
            matches = [m for m in mapping if re.search(r"(^|[_\-.])" + re.escape(m["sample-name"]) + r"([_\-.]|$)", p.name)]
        matches = list({m["sample-id"]: m for m in matches}.values())
        if len(matches) != 1:
            unknown.append(str(p))
        else:
            assigned[matches[0]["sample-id"]].append(p)
    if unknown:
        raise ValueError("Unmatched/ambiguous FASTQ files: " + "; ".join(unknown[:20]))
    prep = Path(prepare_dir)
    prep.mkdir(parents=True, exist_ok=True)
    rows = []
    for sample_id, sources in sorted(assigned.items()):
        if len(sources) > 1:
            if not all(str(p).lower().endswith(".gz") for p in sources):
                raise ValueError("Multiple FASTQs must be all gzipped: " + sample_id)
            target = prep / (sample_id + ".fastq.gz")
            # Concatenating complete gzip members is valid for gzip FASTQ readers.
            with target.open("wb") as out:
                for src in sources:
                    with src.open("rb") as inp:
                        shutil.copyfileobj(inp, out)
        else:
            target = sources[0].resolve()
        rows.append({"sample-id": sample_id, "absolute-filepath": str(target.resolve()),
                     "direction": "forward"})
    write_tsv(output, rows, ["sample-id", "absolute-filepath", "direction"])
    print(json.dumps({"fastq_files": len(files), "matched_samples": len(rows),
                      "unmatched_metadata_samples": len(mapping)-len(rows),
                      "manifest": str(output)}, ensure_ascii=False))
    return rows


def fastq_qc(manifest_path, output, max_reads=0):
    rows = []
    for rec in read_tsv(manifest_path):
        file = rec["absolute-filepath"]
        opener = gzip.open if file.lower().endswith(".gz") else open
        n = 0
        total_bp = 0
        lengths = []
        with opener(file, "rt", encoding="ascii", errors="replace") as f:
            while True:
                h = f.readline()
                if not h:
                    break
                seq, sep, qual = f.readline(), f.readline(), f.readline()
                if not (h.startswith("@") and sep.startswith("+") and len(seq.rstrip()) == len(qual.rstrip())):
                    raise ValueError("Malformed FASTQ record: " + file)
                length = len(seq.rstrip())
                n += 1
                total_bp += length
                if len(lengths) < 10000:
                    lengths.append(length)
                if max_reads and n >= max_reads:
                    break
        lens = sorted(lengths)
        rows.append({"sample-id": rec["sample-id"], "reads": n, "bases": total_bp,
                     "median_length_first_10000": lens[len(lens)//2] if lens else 0})
    write_tsv(output, rows, ["sample-id", "reads", "bases", "median_length_first_10000"])
    print(f"FASTQ QC: {len(rows)} samples => {output}")
    return rows


def load_feature_table(path):
    import pandas as pd
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        first = f.readline()
    df = pd.read_csv(path, sep="\t", comment=None, skiprows=1 if first.startswith("# Constructed") else 0)
    if df.empty:
        raise ValueError("Empty feature table")
    df = df.set_index(df.columns[0])
    df = df.apply(pd.to_numeric, errors="raise").fillna(0)
    if (df < 0).any().any():
        raise ValueError("Negative ASV counts")
    return df


def report(feature_table, taxonomy, metadata, output_dir):
    import pandas as pd
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.spatial.distance import pdist, squareform
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = load_feature_table(feature_table)  # ASVs x samples
    meta = pd.read_csv(metadata, sep="\t").set_index("sample-id")
    common = [s for s in raw.columns if s in meta.index]
    if not common:
        raise ValueError("Zero sample IDs shared by feature table and metadata")
    data = raw.loc[:, common].T
    props = data.div(data.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    richness = (data > 0).sum(axis=1)
    shannon = -(props.where(props > 0, 1).apply(np.log) * props).sum(axis=1)
    alpha = pd.DataFrame({"sample-id": common, "observed_ASVs": richness.values,
                          "shannon": shannon.values, "reads": data.sum(axis=1).values})
    alpha = alpha.merge(meta.reset_index(), on="sample-id", how="left")
    alpha.to_csv(out / "alpha_diversity.csv", index=False)
    if taxonomy:
        taxa = pd.read_csv(taxonomy, sep="\t").set_index("Feature ID")
        taxa = taxa.reindex(raw.index)
        taxa["Taxon"] = taxa["Taxon"].fillna("Unassigned")
        genus = taxa["Taxon"].map(lambda x: (str(x).split(";")[5].strip() if len(str(x).split(";")) > 5 else "Unassigned"))
        genus = genus.replace("", "Unassigned")
        by_genus = data.T.groupby(genus, sort=False).sum().T
        by_genus.to_csv(out / "genus_counts.csv")
        relative = by_genus.div(by_genus.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
        relative.to_csv(out / "genus_relative_abundance.csv")
        top = relative.mean().sort_values(ascending=False).head(15).index
        plot = relative[top].copy()
        plot["Other"] = 1 - plot.sum(axis=1)
        ax = plot.plot(kind="bar", stacked=True, figsize=(max(12, len(common) * 0.18), 6), width=0.85, legend=False)
        ax.set_ylabel("Relative abundance")
        ax.set_xlabel("Sample")
        ax.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize=7)
        plt.tight_layout()
        plt.savefig(out / "genus_stacked_bar.png", dpi=160, bbox_inches="tight")
        plt.close()
    plt.figure(figsize=(max(10, len(common)*0.12), 5))
    plt.bar(range(len(alpha)), alpha["observed_ASVs"])
    plt.xticks(range(len(alpha)), alpha["sample-name"], rotation=90, fontsize=5)
    plt.ylabel("Observed ASVs")
    plt.tight_layout()
    plt.savefig(out / "alpha_richness.png", dpi=160)
    plt.close()
    if len(common) > 1:
        distance = squareform(pdist(data.to_numpy(), metric="braycurtis"))
        distance = np.nan_to_num(distance, nan=0.0)
        pd.DataFrame(distance, index=common, columns=common).to_csv(out / "bray_curtis.csv")
        h = np.eye(len(common)) - np.ones((len(common), len(common))) / len(common)
        b = -0.5 * h @ (distance**2) @ h
        eigenvalues, eigenvectors = np.linalg.eigh(b)
        order = np.argsort(eigenvalues)[::-1]
        values = np.maximum(eigenvalues[order[:2]], 0)
        coords = eigenvectors[:, order[:2]] * np.sqrt(values)
        if coords.shape[1] == 1:
            coords = np.column_stack((coords, np.zeros(len(common))))
        pd.DataFrame({"sample-id": common, "PC1": coords[:, 0], "PC2": coords[:, 1]}).to_csv(out/"pcoa.csv", index=False)
        plt.figure(figsize=(8, 6))
        groups = meta.loc[common, "group-name"].fillna("NA") if "group-name" in meta else meta.loc[common, "cohort"].fillna("NA")
        for cohort in sorted(groups.unique()):
            ids = np.flatnonzero(groups.to_numpy() == cohort)
            plt.scatter(coords[ids, 0], coords[ids, 1], label=cohort, s=28)
        plt.legend()
        plt.xlabel("PCoA 1")
        plt.ylabel("PCoA 2")
        plt.tight_layout()
        plt.savefig(out/"pcoa_bray_curtis.png", dpi=160)
        plt.close()
    summary = {"samples_in_metadata": len(meta), "samples_analyzed": len(common),
               "total_asvs": len(raw), "reads_after_denoising": int(data.to_numpy().sum()),
               "taxonomy_supplied": bool(taxonomy)}
    (out/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    figures = ["alpha_richness.png", "pcoa_bray_curtis.png", "genus_stacked_bar.png"]
    fig_html = "".join('<h2>'+html.escape(x)+'</h2><img style="width:100%;max-width:1400px" src="'+x+'"/>' for x in figures if (out/x).exists())
    table_html = alpha.head(110).to_html(index=False, border=0, classes="stat")
    (out/"report.html").write_text('<!DOCTYPE html><html><meta charset="utf-8"><title>Full-length 16S Report</title>'
        '<style>body{font-family:Arial,sans-serif;max-width:1400px;margin:35px auto;padding:20px;color:#233}'
        '.stat{border-collapse:collapse}.stat td,.stat th{padding:5px 8px;border-bottom:1px solid #ccc}</style>'
        '<h1>PacBio HiFi Full-Length 16S</h1><pre>'+html.escape(json.dumps(summary, indent=2))+'</pre>'
        '<h2>Sample statistics</h2>'+table_html+fig_html+'</html>', encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("samples"); a.add_argument("xlsx"); a.add_argument("output")
    a = sub.add_parser("inspect"); a.add_argument("zip"); a.add_argument("output")
    a = sub.add_parser("manifest"); a.add_argument("fastq_dir"); a.add_argument("metadata"); a.add_argument("output"); a.add_argument("prepare_dir")
    a = sub.add_parser("qc"); a.add_argument("manifest"); a.add_argument("output"); a.add_argument("--max-reads", type=int, default=0)
    a = sub.add_parser("report"); a.add_argument("feature_table"); a.add_argument("metadata"); a.add_argument("output_dir"); a.add_argument("--taxonomy", default=None)
    x = p.parse_args()
    if x.cmd == "samples": samples(x.xlsx, x.output)
    elif x.cmd == "inspect": inspect_zip(x.zip, x.output)
    elif x.cmd == "manifest": manifest(x.fastq_dir, x.metadata, x.output, x.prepare_dir)
    elif x.cmd == "qc": fastq_qc(x.manifest, x.output, x.max_reads)
    elif x.cmd == "report": report(x.feature_table, x.taxonomy, x.metadata, x.output_dir)


if __name__ == "__main__":
    main()
