#!/usr/bin/env python3
"""Reference-aware MW2 mapping for six Day0/Day12 bacterial WGS specimens.

Independent RefSeq loci:
  NC_003923.1 S. aureus MW2 chromosome, 2,820,462 nt
  NC_005011.1 pMW2 plasmid, 20,654 nt

The two contigs are mapped together; a single-reference Day0.1 VCF MUST NOT
be compared by chromosome position to MW2 coordinates without liftover.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Dict

import gatk_haploid_pipeline as g

CHR = "NC_003923.1"
PLASMID = "NC_005011.1"
LENGTHS = {CHR: 2820462, PLASMID: 20654}
REFERENCE_SHA256 = "3a1ec8144b0c10cfd555afd5b3c3af0d15d30d521ee7efbfbb05e86bf87042eb"
OUT_NAME = "mw2_gatk_v1"


def reference_check(root, work, gatk):
    src = root / "outputs/mw2_reference/MW2_chromosome_plasmid.fasta"
    if not src.is_file():
        raise FileNotFoundError("MW2 combined FASTA missing from Drive: " + str(src))
    ref = work / src.name
    if not ref.is_file() or hashlib.sha256(ref.read_bytes()).hexdigest() != REFERENCE_SHA256:
        shutil.copy2(src, ref)
    sha = g.file_sha256(ref)
    if sha != REFERENCE_SHA256:
        raise ValueError("MW2 FASTA SHA256 mismatch. Do not use an unverified reference: " + sha)
    g.call(["samtools", "faidx", ref])
    with (work / (src.name + ".fai")).open(encoding="utf-8") as fh:
        actual = {p[0]: int(p[1]) for p in (line.rstrip().split("\t") for line in fh)}
    if actual != LENGTHS:
        raise ValueError("MW2 accession/length mismatch: " + repr(actual))
    g.call(["bwa", "index", ref])
    dict_path = ref.with_suffix(".dict")
    if not dict_path.is_file():
        g.call([gatk, "CreateSequenceDictionary", "-R", ref, "-O", dict_path])
    return ref, sha


def count_depth_by_contig(bam):
    """Use primary alignments, MQ>=20 and BQ>=20; -aa includes unmapped positions."""
    if not Path(bam).is_file():
        raise FileNotFoundError(bam)
    p = subprocess.Popen(["samtools", "depth", "-aa", "-q", "20", "-Q", "20", str(bam)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8")
    data = {s: {"covered_1x": 0, "covered_10x": 0, "covered_30x": 0,
                "sum_depth": 0, "depth_histogram": Counter(), "positions": 0} for s in LENGTHS}
    for line in p.stdout:
        name, pos, depth = line.rstrip("\n").split("\t", 2)
        if name not in data:
            raise ValueError("Unexpected contig: " + name)
        z = int(depth)
        r = data[name]
        r["positions"] += 1
        r["sum_depth"] += z
        r["covered_1x"] += (z >= 1)
        r["covered_10x"] += (z >= 10)
        r["covered_30x"] += (z >= 30)
        r["depth_histogram"][z] += 1
    err = p.stderr.read()
    if p.wait() != 0:
        raise RuntimeError("samtools depth failed: " + err[-2000:])
    result = {}
    for name, rec in data.items():
        n = LENGTHS[name]
        if rec["positions"] != n:
            raise RuntimeError("Depth does not cover full reference {}: {} of {}".format(name, rec["positions"], n))
        acc = 0
        median = 0
        for depth, cnt in sorted(rec["depth_histogram"].items()):
            acc += cnt
            if acc > (n - 1) // 2:
                median = depth
                break
        result[name] = {"reference_length": n, "mean_depth": round(rec["sum_depth"] / n, 3),
                        "median_depth": median,
                        "breadth_1x": round(rec["covered_1x"] / n, 6),
                        "breadth_10x": round(rec["covered_10x"] / n, 6),
                        "breadth_30x": round(rec["covered_30x"] / n, 6)}
    result["plasmid_chromosome_mean_depth_ratio"] = round(
        result[PLASMID]["mean_depth"] / result[CHR]["mean_depth"], 4
    ) if result[CHR]["mean_depth"] else None
    return result


def collect_coverage(out, selected):
    covdir = out / "coverage"
    covdir.mkdir(parents=True, exist_ok=True)
    merged = {}
    for sample in selected:
        bam = out / "bams" / (sample + ".dedup.bam")
        if not bam.exists():
            raise FileNotFoundError("BAM required for coverage: " + str(bam))
        report = covdir / (sample + ".json")
        result = count_depth_by_contig(bam)
        report.write_text(json.dumps({"sample": sample, "coverage": result,
                                      "mq_min": 20, "bq_min": 20}, indent=2))
        merged[sample] = result
        print("[COVERAGE]", sample,
              "chr", result[CHR]["breadth_10x"],
              "pMW2", result[PLASMID]["breadth_10x"],
              "ratio", result["plasmid_chromosome_mean_depth_ratio"], flush=True)
    return merged


def cds_features(root):
    try:
        from Bio import SeqIO
    except ImportError as ex:
        raise RuntimeError("Install biopython before MW2 CDS annotation") from ex
    by_contig = {}
    for accession in LENGTHS:
        file = root / "outputs/mw2_reference" / (accession + ".gb")
        if not file.exists():
            print("[ANNOTATION HOLD] Missing GenBank:", file, flush=True)
            return {}
        record = SeqIO.read(str(file), "genbank")
        if record.id != accession or len(record.seq) != LENGTHS[accession]:
            raise ValueError("Annotation accession or length mismatch: " + record.id)
        features = []
        for feature in record.features:
            if feature.type != "CDS":
                continue
            # Multipart CDS can be identified by intersection, but partial effects
            # are deliberately not inferred.
            parts = [(int(loc.start), int(loc.end)) for loc in feature.location.parts]
            features.append((parts, feature.qualifiers.get("gene", [""])[0],
                             feature.qualifiers.get("locus_tag", [""])[0],
                             feature.qualifiers.get("product", [""])[0]))
        by_contig[accession] = features
    return by_contig


def annotate_site(contig, pos, ref, alt, annotations):
    start, end = pos - 1, pos - 1 + len(ref)
    genes = []
    for parts, gene, tag, product in annotations.get(contig, []):
        if any(lo < end and hi > start for lo, hi in parts):
            genes.append((gene or tag, tag, product))
    genes = list(dict.fromkeys(genes))
    return {"gene": ";".join(x[0] for x in genes),
            "locus_tag": ";".join(x[1] for x in genes),
            "product": ";".join(x[2] for x in genes),
            "region": "CDS_OVERLAP" if genes else ("INTERGENIC_OR_NONCDS" if annotations else "UNANNOTATED")}


def genotype_group(gt_map, chrom, allele_index, coverage):
    """Conservative screen; not a causal or statistical significance test."""
    if chrom == PLASMID and any(
        coverage.get(s, {}).get(PLASMID, {}).get("breadth_10x", 0) < .8
        for s in g.SAMPLES
    ):
        return "PLASMID_CALLABILITY_REVIEW"
    ok_ref = all(gt_map[s]["GT"] == str(0) and gt_map[s]["DP"] >= 10 and gt_map[s]["GQ"] >= 30
                 for s in g.SAMPLES[:3])
    day12 = sum(gt_map[s]["GT"] == str(allele_index) and gt_map[s]["DP"] >= 10
                and gt_map[s]["GQ"] >= 30 for s in g.SAMPLES[3:])
    if ok_ref and day12 >= 2:
        return "DAY12_REPLICATED_CANDIDATE"
    if ok_ref and day12 == 1:
        return "DAY12_SINGLE_REVIEW"
    if not ok_ref:
        return "BASELINE_OR_CALLABILITY_REVIEW"
    return "OTHER"


def make_joint_report(root, out, joint, coverage):
    import pysam
    co = out / "cohort"
    co.mkdir(parents=True, exist_ok=True)
    ann = cds_features(root)
    csvfile = co / "mw2_variant_candidates.csv"
    fields = ["reference", "pos", "ref", "alt", "type", "qual",
              "region", "gene", "locus_tag", "product", "classification"]
    fields += [s + "_" + x for s in g.SAMPLES for x in ("GT", "DP", "GQ", "AD")]
    counts = Counter()
    with pysam.VariantFile(str(joint)) as vf, csvfile.open("w", newline="", encoding="utf-8") as fh:
        if tuple(vf.header.samples) != g.SAMPLES:
            raise ValueError("VCF samples are not the six expected specimens")
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for record in vf:
            if record.contig not in LENGTHS:
                raise ValueError("Unexpected accession " + record.contig)
            for allele_index, alt in enumerate(record.alts or (), 1):
                if alt.startswith("<") or alt == "*":
                    continue
                genotypes = {}
                for sample in g.SAMPLES:
                    s = record.samples[sample]
                    tup = s.get("GT") or ()
                    gt = str(tup[0]) if len(tup) == 1 and tup[0] is not None else "."
                    dp, gq, ad = s.get("DP"), s.get("GQ"), s.get("AD")
                    genotypes[sample] = {
                        "GT": gt,
                        "DP": int(dp) if dp is not None else 0,
                        "GQ": int(gq) if gq is not None else 0,
                        "AD": ",".join(map(str, ad)) if ad else ""}
                cls = genotype_group(genotypes, record.contig, allele_index, coverage)
                d = {"reference": record.contig, "pos": record.pos, "ref": record.ref,
                     "alt": alt, "type": "SNP" if len(record.ref) == len(alt) == 1 else "INDEL",
                     "qual": record.qual if record.qual is not None else "",
                     "classification": cls,
                     **annotate_site(record.contig, record.pos, record.ref, alt, ann)}
                d.update({s + "_" + k: v for s, gts in genotypes.items() for k, v in gts.items()})
                writer.writerow(d)
                counts[(record.contig, cls)] += 1
    outcome = {
        "analysis": "MW2 chromosome+pMW2 plasmid / 6 haploid specimens",
        "status": "PASS",
        "reference_contigs": LENGTHS, "reference_fasta_sha256": REFERENCE_SHA256,
        "sample_count": len(g.SAMPLES),
        "annotation": "NCBI GenBank CDS overlap" if ann else "NOT AVAILABLE",
        "candidate_counts": {a + "|" + b: num for (a, b), num in sorted(counts.items())},
        "coverage": coverage,
        "warnings": [
            "All VCF coordinates are MW2 references. Old Day0.1 VCF positions cannot be joined without liftover.",
            "Variants relative to MW2 are not automatically Day12-acquired variants.",
            "Fixed haploid GATK genotypes do not estimate minor allele frequencies.",
            "GATK GQ/DP rules are prioritization screens; inspect mapping repeats, strand bias and indel context.",
            "pMW2 presence and copy estimates require breadth/depth and assembly alignment; genotype alone is insufficient.",
            "Antibiotic phenotype/MIC cannot be inferred from these calls alone."
        ]}
    (co / "mw2_summary.json").write_text(json.dumps(outcome, indent=2))
    return outcome


def screen_assemblies(root, out, ref, selected):
    exe = shutil.which("minimap2")
    if exe is None:
        print("[SKIP] minimap2 not available; assembly similarity screen is optional", flush=True)
        return
    results = {}
    target = root / "outputs/mw2_reference" / (PLASMID + ".fasta")
    for sample in selected:
        src = root / "02.Assembly" / sample / (sample + ".seq")
        if not src.is_file():
            results[sample] = {"status": "ASSEMBLY_UNAVAILABLE"}
            continue
        paf = out / "assembly_plasmid" / (sample + ".pMW2.paf")
        paf.parent.mkdir(parents=True, exist_ok=True)
        with paf.open("wb") as fh:
            cp = subprocess.run([exe, "-x", "asm5", "-c", "-t", "2", str(target), str(src)],
                                stdout=fh, stderr=subprocess.PIPE)
        if cp.returncode:
            raise RuntimeError("minimap2 failed for " + sample + ": " + cp.stderr.decode()[-1000:])
        intervals = []
        match_bp, aligned_bp = 0, 0
        for line in paf.read_text().splitlines():
            p = line.split("\t")
            if len(p) >= 12 and p[5] == PLASMID:
                intervals.append((int(p[7]), int(p[8])))
                match_bp += int(p[9])
                aligned_bp += int(p[10])
        merged = []
        for s, e in sorted(intervals):
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        breadth = sum(e - s for s, e in merged) / LENGTHS[PLASMID]
        results[sample] = {"status": "SCREEN_ONLY", "plasmid_reference_breadth": round(breadth, 6),
                           "aggregate_pairwise_identity": round(match_bp / aligned_bp, 6) if aligned_bp else None,
                           "alignment_records": len(intervals)}
        print("[ASSEMBLY]", sample, results[sample], flush=True)
    (out / "assembly_plasmid" / "summary.json").write_text(json.dumps(results, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(g.ROOT))
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--skip-install", action="store_true")
    ap.add_argument("--skip-assembly", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)
    out = root / "outputs" / OUT_NAME
    out.mkdir(parents=True, exist_ok=True)
    work = Path("/content/day0_day12_mw2_work")
    work.mkdir(exist_ok=True)
    exe = work / ("gatk-" + g.GATK_VERSION) / "gatk" if args.skip_install else g.install_tools(work)
    ref, sha = reference_check(root, work, exe)
    selected = g.SAMPLES[:1] if args.pilot else g.SAMPLES
    for sample in selected:
        bam = out / "bams" / (sample + ".dedup.bam")
        status = out / "samples" / sample / "status.json"
        if status.exists() and not bam.exists():
            status.unlink()  # Recreate sample result with its BAM if a prior run omitted it
        g.one_sample(sample, root, out, work, ref, sha, exe, keep_bam=True)
    coverage = collect_coverage(out, selected)
    if not args.skip_assembly:
        screen_assemblies(root, out, ref, selected)
    if args.pilot:
        print("[PILOT PASS] Day0.1 alignment, GVCF, and chromosome/plasmid breadth available", flush=True)
    else:
        joint = g.cohort(out, work, ref, exe)
        summary = make_joint_report(root, out, joint, coverage)
        print(json.dumps({"status": summary["status"],
                          "candidate_counts": summary["candidate_counts"]}, indent=2))


if __name__ == "__main__":
    main()
