#!/usr/bin/env python3
"""Freeze one external v2 HCC venous lesion per independent subject by source size.

This stage NEVER downloads image arrays, computes any radiomic values or accepts
a lesion based on image response; exactly 90 source-verified venous HCC mask
candidates in 59 independent subjects (original Zenodo 21992461). Highest
numeric original Lesion size in mm wins within each subject, tie lowest lesion
index. Missing size in any candidate in a subject => HOLD, not guessed.
"""
import argparse,csv,hashlib,io,json,zipfile
from collections import Counter,defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

REC="https://zenodo.org/records/21992461"
SOURCE_ARTIFACT_ID=13048738836
SOURCE_SHA={
"openswisshcc_v2_external_hcc_venous_access_preflight.json":"c928c2dcd23df70dca80ab560fba78657ea0867eb79d7a162e1d8980f4a08693",
"openswisshcc_v2_venous_hcc_mask_candidate_manifest.csv":"2ab07d78df1c01b35de17218356d9423d384e503409187f9de0227a433536622"}
PARTICIPANTS_MD5="e3df2cc4a825828d0fafdd09155a97c9"
OUTPUT_COLUMNS=("subject","selected_lesion","source_lesion_size_mm","source_mask_path",
"second_reader_mask_present","all_HCC_venous_mask_candidates_in_subject",
"selection_rule","selection_status","original_source_artifact","radiomics_tests_executed",
"clinical_eligible","claim_ceiling")
def read_tsv(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")),delimiter="\t"))
def read_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf8"))))
def sources(path):
    with zipfile.ZipFile(path) as z:
        if set(z.namelist())!=set(SOURCE_SHA):
            raise ValueError("PUBLISHED_HCC_MASK_MANIFEST_ARCHIVE_MEMBER_DRIFT")
        data={k:z.read(k) for k in SOURCE_SHA}
    for k,h in SOURCE_SHA.items():
        if hashlib.sha256(data[k]).hexdigest()!=h:
            raise ValueError("PINNED_EXTERNAL_90_LESION_SOURCE_SHA256_DRIFT:"+k)
    rows=read_csv(data["openswisshcc_v2_venous_hcc_mask_candidate_manifest.csv"])
    summary=json.loads(data["openswisshcc_v2_external_hcc_venous_access_preflight.json"])
    if (len(rows)!=90 or len({r["subject"] for r in rows})!=59
        or summary["HCC_venous_mask_reported_lesions"]!=90
        or summary["HCC_venous_first_reader_masks_found"]!=90
        or summary["HCC_venous_second_reader_masks_found"]!=8
        or summary["external_radiomics_extractions"]!=0
        or summary["claim_ceiling"]!="S0"):
        raise ValueError("UNVERIFIED_EXTERNAL_HCC_VENOUS_ROSTER")
    if len({(r["subject"],r["lesion"]) for r in rows})!=90 or any(
        r["HCC_label"]!="1" or r["venous_lesion_first_mask_path"]==""
        or r["mask_in_derivative_zip"]!="YES" or
        r["image_mask_geometry_verified"]!="NOT_ASSESSED" or
        r["external_radiomics_extraction"]!="NOT_EXECUTED" for r in rows):
        raise ValueError("EXTERNAL_HCC_SOURCE_OR_ANNOTATION_FALSE_APPROVAL")
    return rows
def select(rows,participants):
    keyed={}
    for r in participants:
        pid=r["ID"].strip();n=r["Lesion index"].strip()
        if n=="":
            continue
        if not n.isdigit():raise ValueError("INVALID_OFFICIAL_PARTICIPANT_LESION_INDEX")
        key=(pid,"L"+str(int(n)))
        if key in keyed:raise ValueError("DUPLICATED_PUBLISHED_PARTICIPANT_LESION")
        keyed[key]=r
    by=defaultdict(list)
    for row in rows:
        key=row["subject"],row["lesion"]
        p=keyed.get(key)
        if p is None or p["HCC"]!="1":
            raise ValueError("VENOUS_MASK_HCC_LABEL_MISSING_FROM_ORIGINAL_PARTICIPANTS")
        size=p["Lesion size"].strip()
        try:
            measure=Decimal(size) if size else None
            if measure is not None and (not measure.is_finite() or measure<=0):
                measure=None
        except InvalidOperation:
            measure=None
        by[key[0]].append((row,measure))
    selected=[];holds=[];allrows=[]
    for pid in sorted(by):
        vals=by[pid]
        if len({r["lesion"] for r,_ in vals})!=len(vals):
            raise ValueError("DUPLICATED_EXTERNAL_VENOUS_LESION_IN_PATIENT")
        unresolved=any(v is None for _,v in vals)
        candidate=None if unresolved else sorted(vals,key=lambda x:(
            -x[1],int(x[0]["lesion"][1:])))[0]
        for row,val in vals:
            chosen=candidate is not None and candidate[0]["lesion"]==row["lesion"]
            allrows.append(dict(subject=pid,lesion=row["lesion"],
                lesion_size_mm="" if val is None else str(val),
                mask_member=row["venous_lesion_first_mask_path"],
                selected_primary=bool(chosen),
                status="HOLD_MISSING_LESION_SIZE" if unresolved else
                    "SELECTED_BY_ORIGINAL_MAX_SIZE" if chosen else "SECONDARY_LESION",
                image_mask_geometry="NOT_ASSESSED",clinical_eligible="NOT_ASSESSED",claim_ceiling="S0"))
        if candidate is None:
            holds.append(pid)
            continue
        r,value=candidate
        selected.append(dict(subject=pid,selected_lesion=r["lesion"],
            source_lesion_size_mm=str(value),
            source_mask_path=r["venous_lesion_first_mask_path"],
            second_reader_mask_present="YES" if r["venous_lesion_second_mask_path"] else "NO",
            all_HCC_venous_mask_candidates_in_subject=len(vals),
            selection_rule="LARGEST_PUBLISHED_LESION_SIZE_MM_TIE_LOWEST_L_INDEX",
            selection_status="METADATA_PRESELECTED_ONLY_PENDING_IMAGE_MASK_ALIGNMENT",
            original_source_artifact=SOURCE_ARTIFACT_ID,
            radiomics_tests_executed="NO",clinical_eligible="NOT_ASSESSED",claim_ceiling="S0"))
    if len(allrows)!=90 or len(by)!=59 or len(selected)+len(holds)!=59:
        raise ValueError("SELECTED_SUBJECT_COUNT_OR_SOURCE_UNIVERSE_DRIFT")
    if len({x["subject"] for x in selected})!=len(selected):
        raise ValueError("SELECTED_MULTIPLE_INDEX_TUMORS_FOR_ONE_SUBJECT")
    summary={"status":"PASS_SOURCE_METADATA_ONLY_NO_IMAGE_EXTRACTION",
        "original_source_manifest_artifact":SOURCE_ARTIFACT_ID,
        "original_metadata_record":REC,"HCC_venous_source_lesions":90,
        "independent_subjects_with_venous_masks":59,
        "subjects_with_deterministic_largest_published_lesion":len(selected),
        "subjects_HOLD_missing_any_candidate_lesion_size":len(holds),
        "HOLD_subject_ids":holds,
        "second_reader_primary_subset":sum(x["second_reader_mask_present"]=="YES" for x in selected),
        "source_published_lesion_size_only":True,
        "no_RNA_or_radiomics_outcome_based_lesion_selection":True,
        "actual_original_venous_image_downloaded":False,
        "image_mask_alignment_verified":False,
        "external_radiomics_replication":"NOT_EXECUTED",
        "MRI_RNA_12_tests":"NOT_EXECUTED","clinical_eligible_n":"NOT_ASSESSED",
        "claim_ceiling":"S0"}
    return selected,allrows,summary
def fixture():
    rows=[{"subject":"sub-001","lesion":"L1","venous_lesion_first_mask_path":"a"},
          {"subject":"sub-001","lesion":"L2","venous_lesion_first_mask_path":"b"}]
    p=[{"ID":"sub-001","Lesion index":"1","HCC":"1","Lesion size":"15"},
       {"ID":"sub-001","Lesion index":"2","HCC":"1","Lesion size":"33"}]
    # Synthetic function expects the frozen 59-person universe; this may
    # never be misrepresented as a real cohort run.
    try:select(rows,p)
    except ValueError as e:
        assert "DRIFT" in str(e)
    else:raise AssertionError("ACCEPTED_FABRICATED_59_PATIENT_COHORT")
    p[1]["Lesion size"]=""
    try:select(rows,p)
    except ValueError as e:
        assert "DRIFT" in str(e)
    else:raise AssertionError("MISSING_SIZE_WAS_AUTO_SELECTED")
    print("OPENSWISSHCC_V2_DETERMINISTIC_ONE_LESION_PER_SUBJECT_NEGATIVE_FIXTURE_PASS")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--verified-manifest-zip",type=Path)
    ap.add_argument("--participants",type=Path)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/openswisshcc_primary_lesion_select"))
    a=ap.parse_args()
    if a.offline_test:return fixture()
    if not a.verified_manifest_zip or not a.participants:
        raise ValueError("ORIGINAL_SOURCE_ARTIFACT_AND_MD5_PARTICIPANTS_REQUIRED")
    data=a.participants.read_bytes()
    if hashlib.md5(data).hexdigest()!=PARTICIPANTS_MD5:
        raise ValueError("OFFICIAL_PARTICIPANTS_TSV_MD5_CHANGED")
    first,allrows,summary=select(sources(a.verified_manifest_zip),read_tsv(data))
    a.out_dir.mkdir(parents=True,exist_ok=True)
    with (a.out_dir/"openswisshcc_v2_primary_1_HCC_venous_lesion_per_subject.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=OUTPUT_COLUMNS);w.writeheader();w.writerows(first)
    with (a.out_dir/"openswisshcc_v2_all_90_venous_HCC_lesion_size_and_primary_flags.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    (a.out_dir/"openswisshcc_v2_primary_selection_summary.json").write_text(
       json.dumps(summary,indent=2)+"\n")
    print("OPENSWISSHCC_V2_PRIMARY_PATIENT_DETERMINISTIC_SELECTION",
          json.dumps(summary),flush=True)
if __name__=="__main__":main()
