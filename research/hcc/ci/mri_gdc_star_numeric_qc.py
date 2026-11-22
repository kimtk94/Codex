#!/usr/bin/env python3
"""HCC MRI 14 matched TCGA-LIHC GDC STAR-counts numerical QC (no raw exports).

Downloads small public RNA counts via /data/{UUID}; validates GDC size and MD5,
counts/header/TPM, gene ID consistency, missing/nonfinite/negative data and
per-sample library-size/detection metrics. Original expression vectors are
NEVER included in Git commits or workflow artifacts. Not statistical inference.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

MAX_DOWNLOAD=12*1024*1024
COLS = (
    "patient_id","gdc_file_id","gdc_md5_expected","gdc_md5_verified",
    "file_size_verified","gene_model_annotation","gene_rows",
    "gene_rows_nonzero_unstranded","gene_rows_zero_unstranded",
    "total_unstranded_gene_counts","total_tpm_unstranded",
    "count_missing_or_invalid","tpm_missing_or_invalid",
    "gene_id_duplicates","gene_id_set_consistency",
    "qc_status","review_flags","numerical_rna_qc_eligible_for_pathway","clinical_paired_patient"
)
REQUIRED={"gene_id","gene_name","gene_type","unstranded","tpm_unstranded"}


def fetch_counts(file_id,expected_size):
    if str(uuid.UUID(file_id)) != file_id.lower():
        raise ValueError("Malformed GDC UUID")
    if expected_size<=0 or expected_size>MAX_DOWNLOAD:
        raise ValueError("GDC expected file size exceeds cap")
    url="https://api.gdc.cancer.gov/data/"+file_id
    last=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={
                "Accept-Encoding":"identity",
                "User-Agent":"HCC-MRI-STAR-Counts-Numeric-QC/1.0"})
            with urllib.request.urlopen(req,timeout=60) as response:
                payload=response.read(MAX_DOWNLOAD+1)
            if len(payload)>MAX_DOWNLOAD:
                raise ValueError("GDC file exceeds 12MiB download cap")
            return payload
        except Exception as exc:
            last=exc
            if attempt<2:
                time.sleep(2**attempt)
    raise RuntimeError("GDC download failed: "+str(last))


def parse_star_counts(raw,min_gene_rows=50000):
    try:
        s=raw.decode("utf-8-sig")
    except UnicodeError as e:
        raise ValueError("GDC content is not UTF8 TSV") from e
    model_tags=[]
    tsv=[]
    for line in s.splitlines():
        if line.startswith("#"):
            model_tags.append(line[1:].strip()[:150])
        elif line.strip():
            tsv.append(line)
    reader=csv.DictReader(tsv,delimiter="\t")
    if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
        raise ValueError("Missing GDC STAR fields: "+str(REQUIRED-set(reader.fieldnames or [])))
    seen=set()
    genes=0; expressed=0; counts=0; tpm=0.
    n_invalid=0;t_invalid=0;dup=0
    for row in reader:
        gid=str(row.get("gene_id") or "").strip()
        # STAR's N_unmapped, N_multimapping, N_noFeature, N_ambiguous
        # are non-gene summary lines, not counted as expressed genes.
        if not gid.startswith("ENSG"):
            continue
        genes+=1
        if gid in seen:
            dup+=1
        seen.add(gid)
        try:
            value=int(row["unstranded"])
            if value<0:raise ValueError("Negative gene counts")
            counts+=value
            expressed+=value>0
        except (TypeError,ValueError):
            n_invalid+=1
        try:
            value_tpm=float(row["tpm_unstranded"])
            if not math.isfinite(value_tpm) or value_tpm<0:
                raise ValueError("Bad TPM")
            tpm+=value_tpm
        except (ValueError,TypeError):
            t_invalid+=1
    if genes<min_gene_rows:
        raise ValueError(f"Gene rows {genes} below expected {min_gene_rows}")
    if dup or n_invalid or t_invalid:
        raise ValueError(f"Invalid gene record: duplicate={dup}, counts={n_invalid}, TPM={t_invalid}")
    if counts<=0 or expressed<=0:
        raise ValueError("Empty or undetected expression counts")
    if not (9e5<tpm<1.1e6):
        raise ValueError(f"Unstranded TPM sum implausible: {tpm}")
    return {
        "gene_model_annotation":"|".join(model_tags)[:240],
        "gene_rows":genes,
        "gene_rows_nonzero_unstranded":expressed,
        "gene_rows_zero_unstranded":genes-expressed,
        "total_unstranded_gene_counts":counts,
        "total_tpm_unstranded":round(tpm,3),
        "count_missing_or_invalid":n_invalid,
        "tpm_missing_or_invalid":t_invalid,
        "gene_id_duplicates":dup,
        "_gene_ids":frozenset(seen),
    }


def evaluate_one(item,raw,min_gene_rows):
    expected_size=int(item["gdc_file_size_bytes"])
    expected_hash=item["gdc_md5sum"].lower()
    if item["patient_file_selection_status"]!="ONE_PRIMARY_TUMOR_FILE_METADATA_CANDIDATE":
        raise ValueError("RNA file-to-patient one-to-one lineage not confirmed")
    if item["file_specific_tumor_lineage_status"]!="PRIMARY_TUMOR_FILE_BARCODE_LINKED":
        raise ValueError("File-associated primary tumor barcode not confirmed")
    if len(raw)!=expected_size:
        raise ValueError(f"Size mismatch expected {expected_size}, actual {len(raw)}")
    digest=hashlib.md5(raw).hexdigest()
    if len(expected_hash)!=32 or digest!=expected_hash:
        raise ValueError("GDC MD5 mismatch")
    p=parse_star_counts(raw,min_gene_rows=min_gene_rows)
    p.update({
        "patient_id":item["patient_id"],
        "gdc_file_id":item["gdc_file_id"],
        "gdc_md5_expected":expected_hash,
        "gdc_md5_verified":"YES",
        "file_size_verified":"YES",
        "gene_id_set_consistency":"PENDING_COHORT_CHECK",
        "qc_status":"PASS_FILE_AND_COUNTS_SCHEMA",
        "review_flags":"",
        "numerical_rna_qc_eligible_for_pathway":"TECHNICAL_READY_NOT_CLINICALLY_ELIGIBLE",
        "clinical_paired_patient":"NOT_ASSESSED",
    })
    return p


def combine(records):
    if not records:
        raise ValueError("No records")
    keyset=records[0]["_gene_ids"]
    all_same=all(r["_gene_ids"]==keyset for r in records)
    vals=[r["total_unstranded_gene_counts"] for r in records]
    mid=statistics.median(vals)
    for r in records:
        r["gene_id_set_consistency"]="PASS" if all_same else "MISMATCH_REQUIRES_REVIEW"
        flags=[]
        if r["total_unstranded_gene_counts"]<mid/2 or r["total_unstranded_gene_counts"]>mid*2:
            flags.append("LIBRARY_SIZE_OUTLIER_REVIEW")
        if r["gene_rows_nonzero_unstranded"]<10000:
            flags.append("LOW_DETECTED_GENE_COUNT_REVIEW")
        r["review_flags"]="|".join(flags)
        if not all_same:
            r["qc_status"]="REVIEW_GENE_ID_SET_MISMATCH"
            r["numerical_rna_qc_eligible_for_pathway"]="NOT_ASSESSED"
    return {
        "status":"PASS_ALL_FILE_NUMERICAL_QC" if all_same else "REVIEW_GENE_SET",
        "patients":len(records),
        "gene_sets_consistent":all_same,
        "genes_per_file":sorted({r["gene_rows"] for r in records}),
        "total_unstranded_counts_median":mid,
        "outlier_review_patients":sum(bool(r["review_flags"]) for r in records),
        "md5_size_counts_schema_pass_patients":sum(r["qc_status"]=="PASS_FILE_AND_COUNTS_SCHEMA" for r in records),
        "qualified_radiogenomics_patients":"NOT_ASSESSED",
        "no_rna_expression_values_archived":True,
        "warning":"Unstranded counts QC is preliminary. No tumor purity, batch, clinical timing, pathway scores or MRI-RNA biological association verified."
    }


def offline_test():
    lines=[
        "# gene-model: GENCODE v36",
        "gene_id\tgene_name\tgene_type\tunstranded\ttmp\t tpm_unstranded".replace("\t ","\t"),
        "ENSG00001.1\tGENE1\tprotein_coding\t10\t0\t400000",
        "ENSG00002.1\tGENE2\tprotein_coding\t20\t0\t600000",
    ]
    content=("\n".join(lines)+"\n").encode()
    parsed=parse_star_counts(content,min_gene_rows=2)
    assert parsed["total_unstranded_gene_counts"]==30
    assert parsed["gene_rows_nonzero_unstranded"]==2
    item={"patient_id":"TCGA-AA-0001","gdc_file_id":str(uuid.uuid4()),
          "gdc_file_size_bytes":str(len(content)),"gdc_md5sum":hashlib.md5(content).hexdigest(),
          "patient_file_selection_status":"ONE_PRIMARY_TUMOR_FILE_METADATA_CANDIDATE",
          "file_specific_tumor_lineage_status":"PRIMARY_TUMOR_FILE_BARCODE_LINKED"}
    result=evaluate_one(item,content,2)
    summary=combine([result])
    assert summary["status"]=="PASS_ALL_FILE_NUMERICAL_QC"
    assert summary["qualified_radiogenomics_patients"]=="NOT_ASSESSED"
    for corrupt in (content+b"x",content.replace(b"10\t0",b"-1\t0")):
        try:
            evaluate_one(item,corrupt,2)
        except ValueError: pass
        else: raise AssertionError("Corrupt GDC data must fail")
    print("HCC_MRI_GDC_STAR_NUMERIC_COUNTS_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",default="artifacts/hcc_mri/tcga_liverhccseg_gdc_star_tumor_rna_manifest.csv")
    ap.add_argument("--output",default="artifacts/hcc_rna_qc")
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    if args.offline_test:
        offline_test();return
    with Path(args.manifest).open(newline="",encoding="utf-8") as f:
        manifest=list(csv.DictReader(f))
    ids=[r["patient_id"] for r in manifest]
    if not manifest or len(ids)!=len(set(ids)):
        raise ValueError("Empty/multiple tumor RNA file manifest: fail closed")
    results=[];errors=[]
    for item in sorted(manifest,key=lambda x:x["patient_id"]):
        try:
            content=fetch_counts(item["gdc_file_id"],int(item["gdc_file_size_bytes"]))
            results.append(evaluate_one(item,content,50000))
        except Exception as e:
            errors.append({"patient_id":item["patient_id"],
                           "error_type":type(e).__name__,
                           "reason":str(e)[:160]})
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    if results:
        summary=combine(results)
    else:
        summary={"status":"NO_VALIDATED_COUNTS","patients":0}
    summary.update({
        "run_utc":datetime.now(timezone.utc).isoformat(),
        "expected_manifest_patients":len(manifest),
        "file_qc_failed_patients":len(errors),
        "errors":errors,
    })
    if errors or len(results)!=len(manifest):
        summary["status"]="PARTIAL_OR_FAILED_FILE_QC"
    with (root/"mri_tcga_gdc_star_counts_numeric_qc.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=COLS,extrasaction="ignore")
        w.writeheader()
        w.writerows([{k:v for k,v in r.items() if not k.startswith("_")}
                     for r in results])
    (root/"mri_tcga_gdc_star_counts_numeric_qc_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if summary["status"]!="PASS_ALL_FILE_NUMERICAL_QC":
        raise SystemExit(1)


if __name__=="__main__":
    main()
