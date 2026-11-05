#!/usr/bin/env python3
"""MRI 14 tumor RNA-only Hallmark score QC for redundancy/site/depth.

Never imports MRI features; no image–RNA hypothesis tests or p-values.
Only operates on immutable 14-sample pathway-score table. Spearman rho is
descriptive QC to flag collinear pathway scores and potential TSS confounding.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

SOURCE="research/hcc/HCC_MRI_14_MSIGDB_HALLMARK_RANK_SCORE_20261031.csv"
SETS=(
 "HALLMARK_HYPOXIA","HALLMARK_ANGIOGENESIS",
 "HALLMARK_EPITHELIAL_MESENCHYMAL_TRANSITION","HALLMARK_GLYCOLYSIS",
)

def rank(x):
    x=np.asarray(x,dtype=float)
    order=np.argsort(x,kind="mergesort")
    y=x[order]
    changes=np.r_[0,np.flatnonzero(np.diff(y)!=0)+1,len(x)]
    r=np.empty(len(x),dtype=float)
    for a,b in zip(changes[:-1],changes[1:]):
        r[order[a:b]]=(a+b+1)/2
    return r

def rho(x,y):
    a=rank(x);b=rank(y)
    if np.std(a)<1e-12 or np.std(b)<1e-12:
        raise ValueError("Zero-variance QC field")
    return float(np.corrcoef(a,b)[0,1])

def audit(rows):
    if len(rows)!=14 or len({x["patient_id"] for x in rows})!=14:
        raise ValueError("Patient denominator must be unique 14")
    if any(r["clinical_eligibility"]!="NOT_ASSESSED"
           or r["gdc_file_md5_check"]!="PASS" for r in rows):
        raise ValueError("Clinical status was prematurely changed or MD5 not verified")
    x=np.array([[float(r[s]) for s in SETS] for r in rows])
    if not np.isfinite(x).all() or (x>0.5).any() or (x<-.5).any():
        raise ValueError("RNA score outside documented range")
    pair={}
    flags=[]
    for i,a in enumerate(SETS):
        for j,b in enumerate(SETS):
            if j<=i:continue
            r=rho(x[:,i],x[:,j])
            pair[f"{a}__{b}"]=round(r,6)
            if abs(r)>=0.9:
                flags.append({"pair":[a,b],"spearman_abs":round(abs(r),6),
                              "status":"HIGH_COLLINEARITY_REQUIRES_INTERPRETATION_CAUTION"})
    sites={}
    for s in sorted({r["patient_id"].split("-")[1] for r in rows}):
        idx=[i for i,r in enumerate(rows) if r["patient_id"].split("-")[1]==s]
        sites[s]={"n":len(idx),
                  "median_score_by_pathway":{
                      name:round(float(np.median(x[idx,j])),6)
                      for j,name in enumerate(SETS)}}
    count=np.array([float(r["total_unstranded_gene_counts"]) for r in rows])
    detected=np.array([float(r["detected_genes_unstranded"]) for r in rows])
    return {
      "status":"PASS_RNA_ONLY_SCORE_QC_WITH_COLLINEARITY_FLAGS",
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "n_patients":len(rows),
      "pathway_pair_spearman_descriptive":pair,
      "high_correlation_pairs_abs_ge_0_9":flags,
      "gene_count_spearman_descriptive":{
          name:{"total_unstranded_count_rho":round(rho(x[:,i],count),6),
                "detected_gene_count_rho":round(rho(x[:,i],detected),6)}
          for i,name in enumerate(SETS)},
      "tcga_tissue_source_site_descriptive_medians":sites,
      "note":"No MRI features, outcome labels, clinical eligibility or inferential p-values used. TSS site differences and pathway collinearity require clinical and batch review.",
      "qualified_patient_count":"NOT_ASSESSED",
      "mri_rna_associations_performed":False,
      "manuscript_claim_ceiling":"S0",
    }

def offline_test():
    rows=[]
    for i in range(14):
        rows.append({
          "patient_id":f"TCGA-AA-{i:04d}",
          "clinical_eligibility":"NOT_ASSESSED",
          "gdc_file_md5_check":"PASS",
          "total_unstranded_gene_counts":str(i*1000+1000),
          "detected_genes_unstranded":str(i*500+20000),
          **{s:str(0.02*i+0.001*(j+1)*i*i/14)
             for j,s in enumerate(SETS)},
        })
    o=audit(rows)
    assert o["n_patients"]==14
    assert o["mri_rna_associations_performed"] is False
    assert abs(rho([1,2,3],[1,2,3])-1.)<1e-10
    try:audit(rows[:-1])
    except ValueError:pass
    else:raise AssertionError("Missing patient must fail")
    print("HCC_HALLMARK_RNA_ONLY_REDUNDANCY_OFFLINE_TEST_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--file",default=SOURCE)
    ap.add_argument("--output",default="artifacts/hcc_rna_hallmark_descriptive")
    ap.add_argument("--offline-test",action="store_true")
    a=ap.parse_args()
    if a.offline_test:return offline_test()
    with open(a.file,encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    out=audit(rows)
    p=Path(a.output);p.mkdir(parents=True,exist_ok=True)
    (p/"hcc_mri_hallmark_rna_only_redundancy_qc.json").write_text(
        json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False))

if __name__=="__main__":
    main()
