#!/usr/bin/env python3
"""FASTQ-origin, per-sample amplicon reanalysis with durable stage summaries.
Requirements: fastp, gzip, sort, uniq, bash. Run on Linux (GitHub Actions).
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

STAGES = ["raw", "merge", "unique", "validate"]
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def atomic_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)
def run(args, logfile):
    with logfile.open("a") as log:
        log.write("$ " + " ".join(map(str, args)) + "\n")
        p = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=False)
    if p.returncode: raise RuntimeError(f"Exit {p.returncode}: {' '.join(map(str,args))}")
def fastq_count(path):
    n = 0
    h = hashlib.sha256()
    # Count records and check truncation/sequence quality length; hash compressed source.
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4*1024*1024), b""): h.update(chunk)
    with gzip.open(path, "rb") as f:
        while True:
            header = f.readline()
            if not header: break
            seq, plus, qual = f.readline(), f.readline(), f.readline()
            if not seq or not plus or not qual or not header.startswith(b"@") or not plus.startswith(b"+"):
                raise ValueError(f"Malformed FASTQ at record {n+1}: {path}")
            if len(seq.rstrip(b"\r\n")) != len(qual.rstrip(b"\r\n")):
                raise ValueError(f"Sequence/quality mismatch at record {n+1}")
            n += 1
    return n, h.hexdigest()
def summary(path, data):
    atomic_json(path / "stage_status.json", data)
    cols = ["sample", "stage", "status", "raw_pairs", "merged_reads", "merge_rate", "unique_sequences", "count_sum", "error", "updated_utc"]
    with (path / "summary.tsv.tmp").open("w", newline="") as f:
        w=csv.DictWriter(f, cols, delimiter="\t"); w.writeheader()
        for stage in STAGES:
            record=data["stages"].get(stage, {})
            w.writerow({**{"sample":data["sample"], "stage":stage}, **{k:record.get(k,"") for k in cols if k not in ("sample","stage")}})
    (path / "summary.tsv.tmp").replace(path / "summary.tsv")
    with (path / "summary.md.tmp").open("w") as f:
        f.write(f"# {data['sample']} · FASTQ-origin reanalysis\n\n")
        f.write("| Stage | Status | Raw pairs | Merged reads | Unique | Error |\n|---|---|---:|---:|---:|---|\n")
        for stage in STAGES:
            r=data["stages"].get(stage,{})
            f.write(f"| {stage} | {r.get('status','PENDING')} | {r.get('raw_pairs','')} | {r.get('merged_reads','')} | {r.get('unique_sequences','')} | {str(r.get('error','')).replace('|','/')} |\n")
    (path / "summary.md.tmp").replace(path / "summary.md")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--r1", type=Path, required=True)
    ap.add_argument("--r2", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--threads", type=int, default=4)
    a=ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    data={"sample":a.sample, "source":{"R1":str(a.r1),"R2":str(a.r2)}, "pipeline":"shortread-raw-v1", "stages":{}}
    log=a.output/"pipeline.log"
    raw_pairs=merged_reads=unique=total=0
    def step(name, action):
        data["stages"][name]={"status":"RUNNING","updated_utc":now()}
        summary(a.output,data)
        try:
            values=action()
            data["stages"][name]={**values,"status":"PASS","updated_utc":now()}
        except Exception as e:
            data["stages"][name]={"status":"FAIL","error":str(e),"updated_utc":now()}
            summary(a.output,data)
            raise
        summary(a.output,data)
    def raw():
        nonlocal raw_pairs
        n1,h1=fastq_count(a.r1); n2,h2=fastq_count(a.r2)
        if n1 != n2: raise ValueError(f"R1/R2 count mismatch: {n1} vs {n2}")
        raw_pairs=n1
        return {"raw_pairs":n1,"r1_reads":n1,"r2_reads":n2,"sha256_r1":h1,"sha256_r2":h2}
    def merge():
        nonlocal merged_reads
        merged=a.output/"merged.fastq.gz"
        run(["fastp","-i",str(a.r1),"-I",str(a.r2),"-m",
             "--merged_out",str(merged),"-o",str(a.output/"unmerged_R1.fastq.gz"),"-O",str(a.output/"unmerged_R2.fastq.gz"),
             "-w",str(a.threads),"-j",str(a.output/"fastp.json"),
             "-h",str(a.output/"fastp.html")],log)
        merged_reads=fastq_count(merged)[0]
        return {"raw_pairs":raw_pairs,"merged_reads":merged_reads, "merge_rate":round(merged_reads/raw_pairs,8) if raw_pairs else 0}
    def unique_stage():
        nonlocal unique,total
        merged=a.output/"merged.fastq.gz"
        table=a.output/"unique_sequences.csv.gz"
        # pipeline uses pipefail; failures must not be silently treated as valid empty tables
        cmd="set -o pipefail; gzip -cd -- \"$1\" | awk 'NR%4==2 {print toupper($0)}' | LC_ALL=C sort -T \"$2\" -S 512M | uniq -c | awk '{n=$1; $1=\"\"; sub(/^ /,\"\"); print $0 \"\\t\" n}'"
        temp=a.output/"unique.tsv"
        with temp.open("wb") as f:
            p=subprocess.run(["bash","-c",cmd,"_",str(merged),str(a.output)],stdout=f,stderr=subprocess.PIPE)
        if p.returncode: raise RuntimeError("Unique sort failed: "+p.stderr.decode(errors="replace")[-2000:])
        with temp.open() as inp, gzip.open(table,"wt",newline="") as fout:
            w=csv.writer(fout); w.writerow(["sequence","count","length"])
            for line in inp:
                seq,cnt=line.rstrip("\n").rsplit("\t",1)
                c=int(cnt); w.writerow([seq,c,len(seq)]);unique+=1;total+=c
        temp.unlink()
        return {"unique_sequences":unique,"count_sum":total}
    def validate():
        with gzip.open(a.output/"unique_sequences.csv.gz","rt",newline="") as f:
            rows=csv.DictReader(f)
            n=0; csum=0
            for row in rows:
                n+=1; c=int(row["count"]); csum+=c
                if len(row["sequence"])!=int(row["length"]) or c<=0:
                    raise ValueError(f"Invalid unique row {n}")
        if csum!=merged_reads or n!=unique: raise ValueError(f"Count mismatch: {csum} != {merged_reads} or unique {n} != {unique}")
        return {"count_sum":csum,"merged_reads":merged_reads,"unique_sequences":n,"count_conserved":True}
    for name,fn in [("raw",raw),("merge",merge),("unique",unique_stage),("validate",validate)]:
        step(name,fn)
if __name__=="__main__": main()
