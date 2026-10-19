"""Fail-closed QC of recovered CKD result tables; no scientific re-analysis."""
import argparse,csv,hashlib,json,math
from pathlib import Path
FILES=("STAGE2B_COLOC_DEFAULT.tsv","STAGE2B_COLOC_SUMMARY.tsv","STAGE2C_SUSIE_DEFAULT.tsv","STAGE2C_SUSIE_FAILURES.tsv","STAGE2C_LD_QC.tsv","STAGE3A_KIDNEY_EVIDENCE.tsv","STAGE3B_INTEGRATED_EVIDENCE.tsv","STAGE3B_KIDNEY_LOCALIZATION.tsv")
def run(root):
    tables={}; evidence={}
    for name in FILES:
        p=root/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size>5_000_000: raise ValueError("missing_or_unsafe:"+name)
        with p.open(encoding="utf-8-sig",newline="") as f:
            reader=csv.DictReader(f,delimiter="\t");tables[name]=list(reader)
        if not tables[name]:raise ValueError("empty:"+name)
        evidence[name]={"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"rows":len(tables[name])}
    base={x["gene_symbol"]:x for x in tables[FILES[0]]}
    assert len(base)==9, "unexpected candidate count"
    for name in (FILES[2],FILES[5],FILES[6],FILES[7]):
        if {x["gene_symbol"] for x in tables[name]}!=set(base):raise ValueError("gene_set_mismatch:"+name)
    for name in FILES[:2]:
        for row in tables[name]:
            pp=[float(row["PP.H"+str(i)]) for i in range(5)]
            if not all(math.isfinite(v) and 0<=v<=1 for v in pp) or abs(sum(pp)-1)>0.001:raise ValueError("invalid_posterior")
    for r in tables[FILES[2]]:
        if abs(float(r["stage2b_ABF_PP.H4"])-float(base[r["gene_symbol"]]["PP.H4"]))>1e-8: raise ValueError("abf_mismatch")
    a={x["gene_symbol"]:x for x in tables[FILES[5]]}
    b={x["gene_symbol"]:x for x in tables[FILES[6]]}
    shared=set(next(iter(a.values())))&set(next(iter(b.values())))
    for gene in a:
        for field in shared:
            if a[gene][field]!=b[gene][field]:raise ValueError("stage3_mismatch")
    return {"status":"PASS","files":evidence,"genes":sorted(base),
            "susie_missing":[r["gene_symbol"] for r in tables[FILES[2]] if r["max_PP.H4"] in ("NA","")],
            "scientific_replication":False,"scope":"original_output_integrity_only"}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);p.add_argument("--out",type=Path,default=Path("artifacts/ckd-recovery-qc.json"));a=p.parse_args()
    result=run(a.root);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))
