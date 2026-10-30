#!/usr/bin/env python3
"""PanCanAtlas ABSOLUTE tumor purity provenance audit for 14 MRI/RNA TCGA-LIHC cases.

Official NCI file: TCGA_mastercalls.abs_tables_JSedit.fixed.txt,
https://api.gdc.cancer.gov/data/4f277128-f793-4354-a13d-30cc7fe9f6b5

Match barcode hierarchy explicitly:
    patient (12 chars) < specimen (16 chars) < aliquot.
The RNA aliquot ends in R (RNA); ABSOLUTE normally derives from DNA and
must NEVER be called the same RNA aliquot just because patient IDs match.

On unresolved ambiguity, write all source row candidates and mark REVIEW, NOT PASS.
This QC does not establish pretreatment MRI eligibility and does not associate
radiomics with molecular outcomes.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import urllib.request
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

URL="https://api.gdc.cancer.gov/data/4f277128-f793-4354-a13d-30cc7fe9f6b5"
FILENAME="TCGA_mastercalls.abs_tables_JSedit.fixed.txt"
INPUT="research/hcc/HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv"
MAX_BYTES=8*1024*1024
TCGA=re.compile(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}(?:-[A-Z0-9]{2}[A-Z0-9](?:-[A-Z0-9-]+)?)?",re.I)
FIELDS=("patient_id","rna_sample_barcode","rna_aliquot_barcode","absolute_row_count",
        "same_sample_barcode_row_count","same_tumor_sample_code_row_count",
        "absolute_source_barcodes","absolute_purity_values",
        "absolute_ploidy_values","source_match_granularity",
        "purity_status","clinical_eligibility","review_note")


def fetch_bytes():
    req=urllib.request.Request(URL,headers={"Accept-Encoding":"identity",
        "User-Agent":"HCC-ABSOLUTE-TCGA-Sample-Identity-QC/1.0"})
    with urllib.request.urlopen(req,timeout=65) as resp:
        data=resp.read(MAX_BYTES+1)
    if not 1000<len(data)<MAX_BYTES:
        raise ValueError("Unexpected ABSOLUTE file size")
    return data


def load_manifest(path=INPUT):
    with open(path,newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=14 or len({r["patient_id"] for r in rows})!=14:
        raise ValueError("Expected 14 unique frozen MRI RNA cases")
    for row in rows:
        barcode=row["aliquot_barcode"].upper()
        if not barcode.startswith(row["patient_id"]+"-01"):
            raise ValueError("RNA aliquot not verified Primary Tumor")
    return sorted(rows,key=lambda x:x["patient_id"])


def choose_fields(names):
    # Read actual official header, do not invent schema.
    norm=lambda s: re.sub(r"[^a-z0-9]","",str(s).lower())
    mapping={norm(f):f for f in names}
    purity=[mapping.get(norm(x)) for x in ("Purity","purity","cellularity",
             "absolute_purity","purity_estimate") if mapping.get(norm(x))]
    ploidy=[mapping.get(norm(x)) for x in ("Ploidy","ploidy","absolute_ploidy")
            if mapping.get(norm(x))]
    if not purity:
        raise ValueError("No recognizable ABSOLUTE purity field: "+str(names[:18]))
    preferred=[f for f in names if norm(f) in (
        "sample","samplename","tumorsamplebarcode","tumorsample",
        "array","sampleid","samplebarcode","sampleidentifier","sampleid", "samplecode")]
    return purity[0],ploidy[0] if ploidy else None,preferred


def parse_source(raw):
    content=raw.decode("utf-8-sig")
    lines=[s for s in content.splitlines() if s.strip()]
    if not lines:raise ValueError("ABSOLUTE source empty")
    delim="\t" if lines[0].count("\t") >= lines[0].count(",") else ","
    reader=csv.DictReader(lines,delimiter=delim)
    if not reader.fieldnames:
        raise ValueError("Missing ABSOLUTE header")
    headers=[x.strip() for x in reader.fieldnames]
    purity_field,ploidy_field,id_fields=choose_fields(headers)
    records=[]
    n_no_barcode=0
    for r in reader:
        if not isinstance(r,dict):raise ValueError("Invalid ABSOLUTE row")
        raw_id="|".join(str(r.get(x) or "") for x in id_fields)
        # Fallback searches all fields only when canonical ID fields don't
        # expose a TCGA patient barcode; this is explicitly logged as heuristic.
        ids={m.group(0).upper() for m in TCGA.finditer(raw_id)}
        if not ids:
            raw_id="|".join(str(x or "") for x in r.values())
            ids={m.group(0).upper() for m in TCGA.finditer(raw_id)}
        if not ids:
            n_no_barcode+=1
            continue
        p=str(r.get(purity_field) or "").strip()
        try:
            value=float(p)
        except (TypeError,ValueError):
            continue
        if not math.isfinite(value) or not (0<value<=1):
            raise ValueError("ABSOLUTE purity outside (0,1]")
        ploidy=None
        if ploidy_field:
            try:
                n=float(r.get(ploidy_field) or "")
                if math.isfinite(n) and 0<n<20:ploidy=n
            except (TypeError,ValueError):pass
        for barcode in ids:
            if len(barcode)<12:
                continue
            records.append({"barcode":barcode,"patient":barcode[:12],
                            "sample":barcode[:16] if len(barcode)>=16 else "",
                            "purity":value,"ploidy":ploidy})
    if len(records)<1000:
        raise ValueError("Too few usable PanCancer ABSOLUTE barcode rows")
    return records,{
        "headers":headers,"purity_column":purity_field,
        "ploidy_column":ploidy_field,"identity_columns":id_fields,
        "records_with_extracted_barcode":len(records),
        "records_without_barcode":n_no_barcode,
    }


def join(manifest,records):
    by_patient={}
    for x in records:by_patient.setdefault(x["patient"],[]).append(x)
    out=[]
    for patient in manifest:
        pid=patient["patient_id"]
        rna=patient["aliquot_barcode"].upper()
        sample=rna[:16]
        matches=by_patient.get(pid,[])
        same_sample=[x for x in matches if x["sample"]==sample]
        same_tumor=[x for x in matches if x["sample"].startswith(pid+"-01")]
        candidate=same_sample if same_sample else same_tumor if same_tumor else matches
        if not matches:
            status="NO_ABSOLUTE_PATIENT"
            grain="NONE"
        elif same_sample:
            grain="SAME_TCGA_16_CHAR_SPECIMEN_NOT_SAME_ALIQUOT"
            if len(same_sample)==1:
                status="SAME_SPECIMEN_DNA_PURITY_PROXY"
            elif len({round(x["purity"],7) for x in same_sample})==1:
                status="DUPLICATE_SAME_SPECIMEN_IDENTICAL_VALUES_REVIEW"
            else:
                status="AMBIGUOUS_MULTIPLE_SAME_SPECIMEN_PURITY"
        elif same_tumor:
            grain="SAME_PATIENT_OTHER_PRIMARY_TUMOR_SPECIMEN"
            status="OTHER_TUMOR_SPECIMEN_NOT_RNA_MATCH"
        else:
            grain="PATIENT_ONLY"
            status="PATIENT_ONLY_NOT_SAMPLE_MATCH"
        out.append({
            "patient_id":pid,"rna_sample_barcode":sample,
            "rna_aliquot_barcode":rna,
            "absolute_row_count":len(matches),
            "same_sample_barcode_row_count":len(same_sample),
            "same_tumor_sample_code_row_count":len(same_tumor),
            "absolute_source_barcodes":"|".join(sorted({x["barcode"] for x in candidate})),
            "absolute_purity_values":"|".join(str(round(v,6)) for v in
                        sorted({x["purity"] for x in candidate})),
            "absolute_ploidy_values":"|".join(str(round(v,6)) for v in
                        sorted({x["ploidy"] for x in candidate if x["ploidy"] is not None})),
            "source_match_granularity":grain,
            "purity_status":status,
            "clinical_eligibility":"NOT_ASSESSED",
            "review_note":"ABSOLUTE DNA copy-number purity proxy, not exact RNA aliquot or MRI lesion purity; clinical timing/reader unresolved."
        })
    return out


def offline_test():
    manifest=[{"patient_id":"TCGA-BC-A10Y",
               "aliquot_barcode":"TCGA-BC-A10Y-01A-11R-A131-07"},
              {"patient_id":"TCGA-G3-AAV7",
               "aliquot_barcode":"TCGA-G3-AAV7-01A-11R-A38B-07"}]
    rec=[{"barcode":"TCGA-BC-A10Y-01A-11D-AAAA-01",
          "patient":"TCGA-BC-A10Y","sample":"TCGA-BC-A10Y-01A",
          "purity":0.75,"ploidy":2.2},
         {"barcode":"TCGA-G3-AAV7-01B-11D-AAAA-01",
          "patient":"TCGA-G3-AAV7","sample":"TCGA-G3-AAV7-01B",
          "purity":0.60,"ploidy":2.1}]
    out=join(manifest,rec)
    assert out[0]["purity_status"]=="SAME_SPECIMEN_DNA_PURITY_PROXY"
    assert out[1]["purity_status"]=="OTHER_TUMOR_SPECIMEN_NOT_RNA_MATCH"
    assert all(x["clinical_eligibility"]=="NOT_ASSESSED" for x in out)
    p,q,f=choose_fields(["Sample","Purity","Ploidy"])
    assert (p,q,f)==("Purity","Ploidy",["Sample"])
    try:choose_fields(["Sample","Nothing"])
    except ValueError:pass
    else:raise AssertionError("Missing source purity column allowed")
    print("HCC_PANCAN_ABSOLUTE_PURITY_SAMPLE_IDENTITY_OFFLINE_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--output",default="artifacts/hcc_purity")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    data=fetch_bytes()
    manifest=load_manifest()
    records,meta=parse_source(data)
    result=join(manifest,records)
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    with (root/"hcc_mri_14_pancan_absolute_purity_crosswalk.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(result)
    summary={
        "status":"PASS_PANCAN_PURITY_IDENTITY_AUDIT_ONLY",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "official_gdc_file_uuid":"4f277128-f793-4354-a13d-30cc7fe9f6b5",
        "official_gdc_url":URL,
        "official_file_name":FILENAME,
        "source_size_bytes":len(data),
        "source_sha256":hashlib.sha256(data).hexdigest(),
        "source_schema":meta,
        "n_frozen_mri_rna_candidates":14,
        "status_counts":dict(Counter(r["purity_status"] for r in result)),
        "same_exact_tcga_16_char_specimen_count":sum(
            r["same_sample_barcode_row_count"]!="" and int(r["same_sample_barcode_row_count"])>0
            for r in result),
        "exact_rna_aliquot_purity_proven_count":0,
        "MRI_RNA_clinically_qualified_n":"NOT_ASSESSED",
        "MRI_RNA_association_tests_performed":False,
        "manuscript_claim_ceiling":"S0",
        "warnings":[
           "ABSOLUTE uses DNA copy-number and is not a purity measure on the selected STAR RNA aliquot.",
           "A 16-char TCGA specimen barcode match suggests shared specimen, not necessarily same portion or analyte.",
           "Patient-only/other-tumor-specimen matches MUST NOT be used as sample-purity covariates without adjudication.",
           "The available file may not include all TCGA cancers, including LIHC; missing is not zero purity."
        ]
    }
    (root/"hcc_mri_14_pancan_absolute_purity_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
