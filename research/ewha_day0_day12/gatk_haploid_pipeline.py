#!/usr/bin/env python3
"""Ewha Day0/Day12 bacterial haploid GATK4 germline SNP/indel calling.

Reads and results stay in the user's Google Drive. No credentials or FASTQs in GitHub.
The Day0.1 assembly is an analysis reference, not a claim of clonal identity.
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import urllib.request
from pathlib import Path

SAMPLES = ("Day0.1", "Day0.2", "Day0.3", "Day12.1", "Day12.2", "Day12.3")
EXPECTED_SHA256 = "9ec43fb7bc9513621ca330fc07c1cb41d8ce30e3561f1be1ce0f47edf818551e"
GATK_VERSION = "4.7.0.0"
ROOT = Path("/content/drive/MyDrive/Day0_Day12_Variant_Calling")
OUT_NAME = "gatk_haploid_v1"


def call(args, log=None, env=None):
    args = [str(a) for a in args]
    print("+", " ".join(args[:14]), flush=True)
    if log is None:
        subprocess.run(args, check=True, env=env)
    else:
        p = Path(log)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write("\n$ " + " ".join(args) + "\n")
            fh.flush()
            subprocess.run(args, stdout=fh, stderr=subprocess.STDOUT, check=True, env=env)


def install_tools(work):
    work.mkdir(parents=True, exist_ok=True)
    wanted = ("bwa", "samtools", "bcftools", "java")
    if any(shutil.which(a) is None for a in wanted):
        call(["apt-get", "update", "-qq"])
        call(["apt-get", "install", "-y", "-qq", "bwa", "samtools", "bcftools",
              "tabix", "openjdk-17-jre-headless", "unzip"])
    gatk_dir = work / ("gatk-" + GATK_VERSION)
    exe = gatk_dir / "gatk"
    if not exe.exists():
        archive = work / ("gatk-" + GATK_VERSION + ".zip")
        url = ("https://github.com/broadinstitute/gatk/releases/download/"
               + GATK_VERSION + "/gatk-" + GATK_VERSION + ".zip")
        if not archive.exists():
            urllib.request.urlretrieve(url, archive)
        call(["unzip", "-qo", archive, "-d", work])
    if not exe.exists():
        raise RuntimeError("GATK executable not present after extraction")
    exe.chmod(0o755)
    call([exe, "--version"])
    return exe


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def prepare_reference(root, work, gatk):
    src = root / "outputs/reference/day0_common_reference.fasta"
    if not src.is_file():
        raise FileNotFoundError(src)
    ref = work / "day0_common_reference.fasta"
    shutil.copy2(src, ref)
    sha = file_sha256(ref)
    if sha != EXPECTED_SHA256:
        raise RuntimeError("Reference SHA mismatch: " + sha)
    call(["samtools", "faidx", ref])
    call(["bwa", "index", ref])
    dictfile = ref.with_suffix(".dict")
    if not dictfile.is_file():
        call([gatk, "CreateSequenceDictionary", "-R", ref, "-O", dictfile])
    with open(str(ref) + ".fai", encoding="utf-8") as fh:
        entries = [x.strip().split("\t") for x in fh if x.strip()]
    if len(entries) != 4 or sum(int(x[1]) for x in entries) != 2822641:
        raise RuntimeError("Unexpected reference contig count or base count")
    return ref, sha


def bwa_sort(ref, r1, r2, sample, bam, log):
    # Explicitly inspect both processes; a failed BWA must not look like a successful sort.
    rg = "@RG\\tID:{0}\\tSM:{0}\\tPL:ILLUMINA\\tLB:{0}\\tPU:L1".format(sample)
    bwa = ["bwa", "mem", "-t", "4", "-R", rg, str(ref), str(r1), str(r2)]
    sort = ["samtools", "sort", "-@", "2", "-m", "768M", "-o", str(bam), "-"]
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("\n$ " + " ".join(bwa) + " | " + " ".join(sort) + "\n")
    with open(log, "ab") as fh:
        p1 = subprocess.Popen(bwa, stdout=subprocess.PIPE, stderr=fh)
        p2 = subprocess.Popen(sort, stdin=p1.stdout, stderr=fh)
        p1.stdout.close()
        rc2 = p2.wait()
        rc1 = p1.wait()
    if rc1 or rc2:
        raise RuntimeError("bwa-sort failed: bwa={} sort={} sample={}".format(rc1, rc2, sample))
    call(["samtools", "quickcheck", "-v", bam])


def verify_gvcf(path, sample):
    import pysam
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    if not Path(str(path) + ".tbi").exists():
        raise FileNotFoundError(str(path) + ".tbi")
    with pysam.VariantFile(str(path)) as f:
        if list(f.header.samples) != [sample]:
            raise RuntimeError("GVCF sample mismatch: " + str(list(f.header.samples)))


def one_sample(sample, root, out, work, ref, sha, gatk, keep_bam):
    raw = root / "01.RawData" / sample
    r1 = raw / (sample + "_L1_1.fq.gz")
    r2 = raw / (sample + "_L1_2.fq.gz")
    for file in (r1, r2):
        if not file.is_file() or file.stat().st_size < 10000:
            raise FileNotFoundError("Missing/empty raw FASTQ: " + str(file))
    final_dir = out / "samples" / sample
    final_dir.mkdir(parents=True, exist_ok=True)
    final = final_dir / (sample + ".g.vcf.gz")
    status_path = final_dir / "status.json"
    fingerprint = {"reference_sha256": sha, "r1_bytes": r1.stat().st_size,
                   "r2_bytes": r2.stat().st_size, "gatk_version": GATK_VERSION}
    if status_path.exists():
        try:
            past = json.loads(status_path.read_text())
            if past.get("status") == "PASS" and all(past.get(k) == v for k, v in fingerprint.items()):
                verify_gvcf(final, sample)
                print("[SKIP]", sample, "previously validated", flush=True)
                return
        except Exception as err:
            print("Re-running stale record:", sample, err, flush=True)
    scratch = work / "samples" / sample
    scratch.mkdir(parents=True, exist_ok=True)
    log = final_dir / "run.log"
    try:
        a = scratch / "R1.fq.gz"
        b = scratch / "R2.fq.gz"
        shutil.copy2(r1, a)
        shutil.copy2(r2, b)
        call(["gzip", "-t", a, b], log)
        sorted_bam = scratch / "sorted.bam"
        dedup_bam = scratch / "dedup.bam"
        bwa_sort(ref, a, b, sample, sorted_bam, log)
        call([gatk, "--java-options", "-Xmx6g", "MarkDuplicates",
              "-I", sorted_bam, "-O", dedup_bam, "-M", scratch / "duplicate_metrics.txt",
              "--CREATE_INDEX", "true", "--VALIDATION_STRINGENCY", "SILENT"], log)
        call(["samtools", "quickcheck", "-v", dedup_bam], log)
        call(["samtools", "flagstat", "-@", "2", "-O", "tsv", dedup_bam], log)
        local_g = scratch / (sample + ".g.vcf.gz")
        call([gatk, "--java-options", "-Xmx6g", "HaplotypeCaller", "-R", ref,
              "-I", dedup_bam, "-O", local_g, "-ERC", "GVCF",
              "--sample-ploidy", "1", "--native-pair-hmm-threads", "2"], log)
        verify_gvcf(local_g, sample)
        shutil.copy2(local_g, final)
        shutil.copy2(str(local_g) + ".tbi", str(final) + ".tbi")
        shutil.copy2(scratch / "duplicate_metrics.txt", final_dir / "duplicate_metrics.txt")
        if keep_bam:
            bam_dir = out / "bams"
            bam_dir.mkdir(exist_ok=True)
            shutil.copy2(dedup_bam, bam_dir / (sample + ".dedup.bam"))
            idx = Path(str(dedup_bam) + ".bai")
            if not idx.exists():
                idx = dedup_bam.with_suffix(".bai")
            shutil.copy2(idx, bam_dir / (sample + ".dedup.bam.bai"))
        verify_gvcf(final, sample)
        status_path.write_text(json.dumps({"sample": sample, "status": "PASS",
                                          **fingerprint}, indent=2))
        print("[PASS]", sample, flush=True)
    except Exception as e:
        status_path.write_text(json.dumps({"sample": sample, "status": "FAILED",
                                           "error": repr(e), **fingerprint}, indent=2))
        traceback.print_exc()
        raise
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def cohort(out, work, ref, gatk):
    import pysam
    gvcfs = [out / "samples" / s / (s + ".g.vcf.gz") for s in SAMPLES]
    for s, g in zip(SAMPLES, gvcfs):
        verify_gvcf(g, s)
        status = json.loads((g.parent / "status.json").read_text())
        if status.get("status") != "PASS":
            raise RuntimeError("Sample has no PASS status: " + s)
    co = out / "cohort"
    co.mkdir(exist_ok=True)
    merged = work / "six_samples.g.vcf.gz"
    raw = work / "joint.raw.vcf.gz"
    norm = co / "joint.normalized.vcf.gz"
    log = co / "joint.log"
    if not norm.is_file() or not Path(str(norm) + ".tbi").is_file():
        call([gatk, "--java-options", "-Xmx6g", "CombineGVCFs", "-R", ref,
              *[x for g in gvcfs for x in ("-V", str(g))], "-O", merged], log)
        call([gatk, "--java-options", "-Xmx6g", "GenotypeGVCFs",
              "-R", ref, "-V", merged, "-O", raw], log)
        call(["bcftools", "norm", "-m", "-any", "-f", ref, "-Oz", "-o", norm, raw], log)
        call(["bcftools", "index", "-t", "-f", norm], log)
    with pysam.VariantFile(str(norm)) as vf:
        if tuple(vf.header.samples) != SAMPLES:
            raise RuntimeError("Unexpected sample order/count in joint VCF")
    return norm


def summarise(vcf, root, out, sha):
    import pysam
    co = out / "cohort"
    csv_path = co / "joint_variant_audit.csv"
    key_path = root / "outputs/lofreq_genomewide_v9_1/lofreq_integrated_candidate_classification.csv"
    lofreq = set()
    if key_path.is_file():
        with key_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if {"chrom", "pos", "ref", "alt"} <= set(reader.fieldnames or []):
                lofreq = {(r["chrom"], int(r["pos"]), r["ref"], r["alt"]) for r in reader}
    n = 0
    replicated = 0
    overlap = 0
    with pysam.VariantFile(str(vcf)) as vf, csv_path.open("w", newline="", encoding="utf-8") as fh:
        fields = ["chrom", "pos", "ref", "alt", "variant_type", "QUAL",
                  "day0_callable", "day12_alt_highconf", "day12_replicated",
                  "lofreq_match", "classification"]
        for s in SAMPLES:
            fields += [s + "_GT", s + "_DP", s + "_GQ", s + "_AD"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for v in vf:
            for alt_idx, alt in enumerate(v.alts or (), 1):
                if alt.startswith("<") or alt == "*":
                    continue
                d = {"chrom": v.contig, "pos": v.pos, "ref": v.ref, "alt": alt,
                     "variant_type": "SNP" if len(v.ref) == len(alt) == 1 else "INDEL",
                     "QUAL": v.qual if v.qual is not None else ""}
                day0_callable = 0
                day12_alt = 0
                for s in SAMPLES:
                    x = v.samples[s]
                    gt = x.get("GT") or ()
                    dp = x.get("DP") or 0
                    gq = x.get("GQ") or 0
                    ad = x.get("AD") or ()
                    d[s + "_GT"] = "/".join("." if z is None else str(z) for z in gt)
                    d[s + "_DP"] = dp
                    d[s + "_GQ"] = gq
                    d[s + "_AD"] = ",".join("." if z is None else str(z) for z in ad)
                    if s.startswith("Day0") and len(gt) == 1 and gt[0] == 0 and dp >= 10 and gq >= 30:
                        day0_callable += 1
                    if s.startswith("Day12") and len(gt) == 1 and gt[0] == alt_idx and dp >= 10 and gq >= 30:
                        day12_alt += 1
                match = (v.contig, v.pos, v.ref, alt) in lofreq
                d["day0_callable"] = day0_callable
                d["day12_alt_highconf"] = day12_alt
                d["day12_replicated"] = int(day12_alt >= 2)
                d["lofreq_match"] = int(match)
                if day0_callable == 3 and day12_alt >= 2 and match:
                    cls = "REPLICATED_AND_LOFREQ"
                elif day0_callable == 3 and day12_alt >= 2:
                    cls = "REPLICATED_GATK_ONLY_REVIEW"
                elif day12_alt == 1:
                    cls = "SINGLE_DAY12_REVIEW"
                elif day0_callable != 3:
                    cls = "DAY0_CALLABILITY_REVIEW"
                else:
                    cls = "OTHER"
                d["classification"] = cls
                writer.writerow(d)
                n += 1
                replicated += (day0_callable == 3 and day12_alt >= 2)
                overlap += match
    summary = {"pipeline": "GATK HaplotypeCaller haploid v1",
               "status": "PASS", "reference_sha256": sha,
               "samples": SAMPLES, "sample_count": len(SAMPLES),
               "gatk_version": GATK_VERSION, "joint_alleles": n,
               "replicated_day12_with_callable_day0": replicated,
               "lofreq_overlap_count": overlap,
               "lofreq_comparison_available": key_path.is_file(),
               "limitations": ["HaplotypeCaller haploid genotypes do not quantify low allele fractions",
                               "Reference is Day0.1 assembly, missing accessory DNA cannot be called",
                               "Reference-mapping/repeat/strand filters still needed",
                               "GATK genotype concordance does not establish causal resistance or SV"] }
    (co / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--pilot", action="store_true", help="Run only Day0.1; no joint genotyping")
    ap.add_argument("--keep-bam", action="store_true", help="Retain six duplicate-marked BAMs in Drive")
    ap.add_argument("--skip-install", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        raise FileNotFoundError("Missing Google Drive project: " + str(root))
    out = root / "outputs" / OUT_NAME
    out.mkdir(parents=True, exist_ok=True)
    work = Path("/content/day0_day12_gatk_work")
    work.mkdir(exist_ok=True)
    if args.skip_install:
        exe = work / ("gatk-" + GATK_VERSION) / "gatk"
        if not exe.is_file():
            raise FileNotFoundError(exe)
    else:
        exe = install_tools(work)
    ref, sha = prepare_reference(root, work, exe)
    selected = SAMPLES[:1] if args.pilot else SAMPLES
    for sample in selected:
        one_sample(sample, root, out, work, ref, sha, exe, args.keep_bam)
    if not args.pilot:
        joint = cohort(out, work, ref, exe)
        summarise(joint, root, out, sha)


if __name__ == "__main__":
    main()
