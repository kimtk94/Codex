#!/usr/bin/env python3
"""Pre-association Hallmark v2025.1.Hs RNA sample-rank score QC, TCGA MRI n=14.

No radiomics feature files loaded; does NOT calculate MRI-RNA correlations.
Outputs small scores and mapping diagnostics, not expression matrices.
All 14 source files are byte-size and MD5 checked before parsing.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from mri_gdc_star_numeric_qc import fetch_counts

GMT_URL="https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2025.1.Hs/h.all.v2025.1.Hs.symbols.gmt"
PATHWAYS=(
    "HALLMARK_HYPOXIA",
    "HALLMARK_ANGIOGENESIS",
    "HALLMARK_EPITHELIAL_MESENCHYMAL_TRANSITION",
    "HALLMARK_GLYCOLYSIS",
)
FROZEN_MANIFEST="research/hcc/HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv"
MIN_COVERAGE=0.70
MIN_GENES=15
SCHEMA={"gene_id","gene_name","gene_type","unstranded","tpm_unstranded"}
SCORE_FIELDS=("patient_id","gene_set_version","rank_universe_symbols",
              "protein_coding_gene_id_rows","duplicate_symbol_conflicts",
              "total_unstranded_gene_counts","detected_genes_unstranded",
              "gdc_file_md5_check","clinical_eligibility",
              *PATHWAYS)


def gmt_parse(raw):
    try:
        text=raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("Official GMT non-UTF8") from e
    all_sets={}
    for line in text.splitlines():
        fields=line.rstrip("\r").split("\t")
        if len(fields)<3:continue
        name=fields[0].strip()
        if name in all_sets:raise ValueError("Duplicate GMT set")
        members=[g.strip() for g in fields[2:] if g.strip()]
        if len(members)!=len(set(members)):
            raise ValueError("Duplicated gene names in GMT set "+name)
        all_sets[name]=members
    if not set(PATHWAYS).issubset(all_sets):
        raise ValueError("Required Hallmark sets not in official GMT")
    if len(all_sets)!=50:
        raise ValueError("Expected 50 official Hallmark genesets; got "+str(len(all_sets)))
    return {key:all_sets[key] for key in PATHWAYS},len(all_sets)


def remote_gmt(expected_sha=None):
    request=urllib.request.Request(GMT_URL,headers={"User-Agent":"HCC-Hallmark-SingleSample-Rank-QC/1.0"})
    with urllib.request.urlopen(request,timeout=45) as r:
        raw=r.read(250000)
    if len(raw)<10000 or len(raw)>=250000:
        raise ValueError("Invalid/suspicious MSigDB GMT download size")
    sha=hashlib.sha256(raw).hexdigest()
    if expected_sha and sha!=expected_sha.lower():
        raise ValueError("Official MSigDB gene set snapshot SHA256 changed")
    sets,n=gmt_parse(raw)
    return sets,sha,n


def average_percentiles(tpm):
    """0..1 percentile of log2(TPM+1), average tie ranks, within each sample."""
    x=np.asarray(tpm,dtype=float)
    if len(x)<3 or not np.isfinite(x).all() or np.any(x<0):
        raise ValueError("Invalid log TPM ranking universe")
    x=np.log2(1.0+x)
    order=np.argsort(x,kind="mergesort")
    ranks=np.empty(len(x),dtype=float)
    sorted_x=x[order]
    changes=np.r_[0,np.flatnonzero(np.diff(sorted_x)!=0)+1,len(x)]
    for begin,end in zip(changes[:-1],changes[1:]):
        ranks[order[begin:end]]=(begin+end+1)/2.0
    return (ranks-1.0)/(len(x)-1.0)


def parse_gdc_expression(raw):
    s=raw.decode("utf-8-sig")
    annotations=[]
    source=[]
    for line in s.splitlines():
        if line.startswith("#"):
            annotations.append(line[1:].strip())
        elif line.strip():
            source.append(line)
    reader=csv.DictReader(source,delimiter="\t")
    if not reader.fieldnames or not SCHEMA.issubset(reader.fieldnames):
        raise ValueError("Unexpected GDC STAR-counts schema")
    genes={}
    seen_ensg=set()
    duplicated_symbols=0
    protein_rows=0
    counts=0
    expressed=0
    total_tpm=0.0
    for row in reader:
        ensg=(row.get("gene_id") or "").strip()
        if not ensg.startswith("ENSG"):continue
        if ensg in seen_ensg:
            raise ValueError("Duplicate GDC ENSG gene ID")
        seen_ensg.add(ensg)
        value=int(row["unstranded"])
        tpm=float(row["tpm_unstranded"])
        if value<0 or not math.isfinite(tpm) or tpm<0:
            raise ValueError("Invalid original GDC count or TPM")
        counts+=value
        expressed+=value>0
        total_tpm+=tpm
        if row.get("gene_type")!="protein_coding":continue
        protein_rows+=1
        symbol=(row.get("gene_name") or "").strip()
        if not symbol:continue
        if symbol in genes:
            duplicated_symbols+=1
            # Rule locked before associations: preserve max TPM for alias.
            genes[symbol]=max(genes[symbol],tpm)
        else:
            genes[symbol]=tpm
    if len(seen_ensg)!=60660 or len(genes)<17000:
        raise ValueError("Unexpected GDC GENCODE gene universe")
    if not 900000<total_tpm<1100000:
        raise ValueError("Full gene TPM total implausible")
    if sum("GENCODE v36" in note for note in annotations)==0:
        raise ValueError("Not documented GENCODE v36 source")
    if not counts>0 or expressed<15000:
        raise ValueError("Unexpected RNA count depth")
    return genes,{
        "all_gene_ids":len(seen_ensg),
        "protein_coding_gene_id_rows":protein_rows,
        "rank_universe_symbols":len(genes),
        "duplicate_symbol_conflicts":duplicated_symbols,
        "total_unstranded_gene_counts":counts,
        "detected_genes_unstranded":expressed,
    }


def score_sample(symbol_tpm,genesets):
    ordered=sorted(symbol_tpm)
    rank=average_percentiles([symbol_tpm[s] for s in ordered])
    pos=dict(zip(ordered,rank))
    out={}
    coverage={}
    for name,members in genesets.items():
        present=[g for g in members if g in pos]
        cov=len(present)/len(members)
        coverage[name]={
            "membership_count":len(members),
            "matched_count":len(present),
            "coverage":round(cov,6),
            "missing_symbols":sorted(set(members)-set(present)),
        }
        if cov<MIN_COVERAGE or len(present)<MIN_GENES:
            raise ValueError(f"Gene-set membership too low {name}: {len(present)}/{len(members)}")
        out[name]=round(float(np.mean([pos[g] for g in present])-0.5),8)
        if not math.isfinite(out[name]) or not -0.5<=out[name]<=0.5:
            raise ValueError("Gene set score outside allowable range")
    return out,coverage


def load_manifest(path):
    with Path(path).open(encoding="utf-8",newline="") as f:
        items=list(csv.DictReader(f))
    ids=[x["patient_id"] for x in items]
    if len(ids)!=14 or len(set(ids))!=14:
        raise ValueError("Require unique, frozen 14 MRI TCGA patient IDs")
    for x in items:
        if not x["aliquot_barcode"].startswith(x["patient_id"]+"-01"):
            raise ValueError("Not linked to Primary Tumor aliquot")
    return sorted(items,key=lambda x:x["patient_id"])


def run(manifest,sets,sha):
    data=[]
    cover=[]
    errors=[]
    for item in manifest:
        pid=item["patient_id"]
        try:
            size=int(item["gdc_file_size_bytes"])
            raw=fetch_counts(item["gdc_file_id"],size)
            if len(raw)!=size or hashlib.md5(raw).hexdigest()!=item["gdc_md5sum"].lower():
                raise ValueError("GDC STAR file size or MD5 mismatch")
            symbols,metrics=parse_gdc_expression(raw)
            scores,cov=score_sample(symbols,sets)
            data.append({
                "patient_id":pid,"gene_set_version":"MSIGDB_HALLMARK_v2025.1.Hs",
                **metrics,"gdc_file_md5_check":"PASS",
                "clinical_eligibility":"NOT_ASSESSED",**scores
            })
            cover.append({"patient_id":pid,"gene_set_coverage":cov})
        except Exception as exc:
            errors.append({"patient_id":pid,"type":type(exc).__name__,"reason":str(exc)[:180]})
    if errors or len(data)!=len(manifest):
        status="FAILED_OR_PARTIAL_SAMPLE_SCORE_QC"
    else:
        if any(max(float(x[p]) for x in data)-min(float(x[p]) for x in data)<1e-8
               for p in PATHWAYS):
            status="BLOCKED_ZERO_SCORE_VARIANCE"
        else:
            status="PASS_4_PATHWAY_SAMPLE_SCORE_QC"
    summary={
        "status":status,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_official_gmt_url":GMT_URL,
        "source_official_gmt_sha256":sha,
        "source_official_gene_set_version":"2025.1.Hs",
        "score_method":"CUSTOM_SINGLE_SAMPLE_MEAN_RANK_PERCENTILE_MINUS_0.5",
        "gene_ranking_universe":"protein_coding, unique_gene_name_by_max_TPM",
        "expression_input":"GDC_STAR_tpm_unstranded_log2p1_for_ranking",
        "n_cases_expected":len(manifest),"n_cases_scored":len(data),
        "n_gene_sets":len(sets),
        "gene_sets":list(PATHWAYS),
        "errors":errors,
        "score_distribution_per_pathway":{
            name:{
                "min":min(float(r[name]) for r in data),
                "median":statistics.median(float(r[name]) for r in data),
                "max":max(float(r[name]) for r in data),
            } for name in PATHWAYS
        } if data else {},
        "minimum_gene_set_coverage_by_pathway":{
            name:min(x["gene_set_coverage"][name]["coverage"] for x in cover)
            for name in PATHWAYS
        } if cover else {},
        "biological_mri_rna_associations_performed":False,
        "qualified_patient_count":"NOT_ASSESSED",
        "claim_ceiling":"S0",
        "limitations":[
            "The score is a documented custom rank score, NOT the original singscore package.",
            "Sample-wise ranking minimizes cohort dependence but not tumor purity or batch confounding.",
            "Hallmark EMT/angiogenesis reflect tumor microenvironment and stromal mixture.",
            "Clinical and ROI eligibility unresolved; NO MRI-radiomics correlations authorized.",
        ],
    }
    return data,cover,summary


def offline_test():
    genesets={
        name:[f"GENE{i}" for i in range(j*16,(j+1)*16)]
        for j,name in enumerate(PATHWAYS)
    }
    symbols={f"GENE{i}":float(i+1) for i in range(80)}
    scores,cov=score_sample(symbols,genesets)
    assert len(scores)==4 and all(v["coverage"]==1.0 for v in cov.values())
    assert scores[PATHWAYS[0]]<scores[PATHWAYS[3]]
    assert np.allclose(average_percentiles([0,0,1,2]),
                       [1/6,1/6,2/3,1])
    try:score_sample({"GENE1":5.},genesets)
    except ValueError:pass
    else:raise AssertionError("Missing gene sets must stop")
    try:gmt_parse(b"HALLMARK_HYPOXIA\tx\tABC\n")
    except ValueError:pass
    else:raise AssertionError("Incomplete GMT must stop")
    content=("# gene-model: GENCODE v36\n"
             "gene_id\tgene_name\tgene_type\tunstranded\ttpm_unstranded\n")
    content+="".join(
        f"ENSG{i:011d}.1\tGENE{i}\tprotein_coding\t10\t10.0\n"
        for i in range(60660))
    genes,m=parse_gdc_expression(content.encode())
    assert m["all_gene_ids"]==60660 and m["rank_universe_symbols"]==60660
    print("HCC_MRI_HALLMARK_RANK_SCORE_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--manifest",default=FROZEN_MANIFEST)
    ap.add_argument("--out-dir",default="artifacts/hcc_rna_hallmark")
    ap.add_argument("--expected-gmt-sha256",default="")
    args=ap.parse_args()
    if args.offline_test:
        offline_test();return
    manifest=load_manifest(args.manifest)
    pathways,sha,n=remote_gmt(args.expected_gmt_sha256)
    data,coverage,summary=run(manifest,pathways,sha)
    summary["official_gmt_gene_set_count"]=n
    out=Path(args.out_dir)
    out.mkdir(parents=True,exist_ok=True)
    with (out/"hcc_mri_14_hallmark_single_sample_scores.csv").open(
            "w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=SCORE_FIELDS)
        writer.writeheader();writer.writerows(data)
    (out/"hcc_mri_hallmark_gene_set_coverage.json").write_text(
        json.dumps(coverage,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"hcc_mri_hallmark_single_sample_qc.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if summary["status"]!="PASS_4_PATHWAY_SAMPLE_SCORE_QC":
        raise SystemExit(1)


if __name__=="__main__":main()
