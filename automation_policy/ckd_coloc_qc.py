"""CKD Stage2B coloc result integrity/shape QC for Drive-exported TSVs.

Use only with explicitly downloaded private files in a trusted workspace.
No publishing or network access. Original files are never committed.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

REQUIRED={"gene_symbol","p1","p2","p12","nsnps","PP.H0","PP.H1","PP.H2","PP.H3","PP.H4"}

def read(path, expected):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>5_000_000:
        raise ValueError("missing_or_unsafe_file")
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if expected and digest!=expected:
        raise ValueError("checksum_mismatch")
    with path.open(newline="",encoding="utf-8-sig") as f:
        r=csv.DictReader(f,delimiter="\t")
        if not REQUIRED.issubset(r.fieldnames or []):
            raise ValueError("missing_required_columns")
        rows=list(r)
    if not rows:
        raise ValueError("empty_result")
    for row in rows:
        if not row["gene_symbol"] or int(row["nsnps"])<1:
            raise ValueError("invalid_gene_or_snp_count")
        pp=[float(row["PP.H"+str(j)]) for j in range(5)]
        if not all(math.isfinite(v) and 0<=v<=1 for v in pp) or abs(sum(pp)-1)>0.001:
            raise ValueError("invalid_coloc_posterior")
        if not all(float(row[p])>0 for p in ("p1","p2","p12")):
            raise ValueError("invalid_prior")
    return rows,digest

def audit(default,summary,expected_default="",expected_summary=""):
    d,dh=read(default,expected_default)
    s,sh=read(summary,expected_summary)
    dkeys={(x["gene_symbol"],x["p1"],x["p2"],x["p12"]) for x in d}
    skeys={(x["gene_symbol"],x["p1"],x["p2"],x["p12"]) for x in s}
    if len(dkeys)!=len(d) or len(skeys)!=len(s) or not dkeys.issubset(skeys):
        raise ValueError("unmatched_or_duplicate_scenarios")
    genes=sorted({r["gene_symbol"] for r in d})
    return {"qc":"PASS","scope":"tabular-integrity-and-coloc-posterior-only",
            "scientific_replication":False,
            "default_sha256":dh,"summary_sha256":sh,
            "default_rows":len(d),"sensitivity_rows":len(s),"genes":genes,
            "default_pph4":{r["gene_symbol"]:float(r["PP.H4"]) for r in d},
            "raw_data_published":False}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--default",type=Path,required=True)
    p.add_argument("--summary",type=Path,required=True)
    p.add_argument("--expected-default",default="")
    p.add_argument("--expected-summary",default="")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=audit(a.default,a.summary,a.expected_default,a.expected_summary)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
