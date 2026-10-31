#!/usr/bin/env python3
"""OpenSwissHCC v2 public-source, MRI-only external validation preflight.

Official record: Zenodo 21992461, version v2 (Aug-Oct 2026).
Read exact-MD5 metadata and (optional) derivative ZIP directory, identify
HCC-specific lesion/venous-mask candidates BEFORE any external MRI radiomics.

Never equate 132 enrolled subjects / 140 lesion annotations / 97 confirmed
HCC lesions with *eligible portal venous HCC mask pairs*. Do not use other
HCC or imaging cohorts as "external" if source patient identities overlap.
No MRI-RNA, clinical eligibility inference, treatment claim or diagnostic model.
"""
import argparse,csv,hashlib,io,json,re,zipfile
from collections import Counter,defaultdict
from pathlib import Path

REC="https://zenodo.org/records/21992461"
PINNED={
 "participants.tsv":"e3df2cc4a825828d0fafdd09155a97c9",
 "annotation_status.tsv":"9fceca660e4d6a74b25ccf172ac380dd",
 "data_description.txt":"7cf6cb8fe20c0b8012c9666bb4dfbfbe",
 "README.md":"1161d2370e3d3bb0f5217daa0a171173",
}
DERIVATIVE_MD5="45975a7018834c4ab1b827efff0b41ac"
MASK_GROUPS=("manual_lesion_annotations/","manual_lesion_annotations_second_reader/",
 "manual_liver_annotations/","automated_liver_annotations/","T1_registration_transforms/")
VALID_STATUS={"annotated","not_visible","not_interpretable","sequence_unavailable",
             "visible_not_annotated","reassessed_after_delineation"}
MASK_PRESENT={"annotated","reassessed_after_delineation"}
SEQUENCES={"T1 native","Arterial","Venous","Delayed","T2","DWI (TRACE)","ADC"}

def decode(path):
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter="\t"))

def pinned_files(folder):
    for name,expected in PINNED.items():
        p=folder/name
        if not p.is_file():raise ValueError("OFFICIAL_METADATA_MISSING:"+name)
        data=p.read_bytes()
        if hashlib.md5(data).hexdigest()!=expected:
            raise ValueError("ZENODO_V2_METADATA_MD5_CHANGED:"+name)
    text=(folder/"README.md").read_text(encoding="utf8")
    if "second" not in text.lower() or "venous" not in text.lower():
        raise ValueError("NOT_VERSION_V2_OPEN_SWISS_HCC_METADATA")

def participant_key(row):
    pid=row.get("ID","").strip()
    lesion=row.get("Lesion index","").strip()
    if not re.fullmatch(r"sub-\d{3}",pid):
        raise ValueError("INVALID_OFFICIAL_SUBJECT_ID")
    # The official participants.tsv includes 69 HCC-negative control subjects
    # with NO lesions (blank lesion index, 0 lesion counts). Preserve these
    # people in the 132-subject cohort, not as fake L0 lesion annotations.
    if lesion=="":
        if row.get("Number of lesions","").strip() not in ("","0") or (
            row.get("Number of HCC lesions","").strip() not in ("","0")):
            raise ValueError("NO_LESION_SUBJECT_WITH_POSITIVE_LESION_COUNT")
        return None
    if not lesion.isdigit() or not 1<=int(lesion)<=5:
        raise ValueError("INVALID_OFFICIAL_LESION_INDEX")
    return (pid,"L"+str(int(lesion)))

def preflight(participants,annots,deriv_names=None):
    part={}
    no_lesion_subjects=set()
    all_subjects=set()
    for row in participants:
        k=participant_key(row)
        all_subjects.add(row["ID"].strip())
        if k is None:
            no_lesion_subjects.add(row["ID"].strip())
            continue
        if k in part:raise ValueError("DUPLICATE_PARTICIPANT_LESION_PAIR")
        part[k]=row
    if not part:raise ValueError("NO_OFFICIAL_PARTICIPANT_LESION_METADATA")
    if no_lesion_subjects & {pid for pid,_ in part}:
        raise ValueError("CONTROL_SUBJECT_HAS_CONFLICTING_LESION_ROWS")
    recorded={}
    for row in annots:
        k=(row.get("subject","").strip(),row.get("lesion","").strip(),
           row.get("sequence","").strip())
        status=row.get("Status","").strip()
        if (k[:2] not in part or k[2] not in SEQUENCES or
            status not in VALID_STATUS or k in recorded):
            raise ValueError("ANNOTATION_REFERENCE_OR_STATUS_INVALID:"+repr(k))
        recorded[k]=status
    if not recorded:raise ValueError("NO_V2_ANNOTATION_STATUS_ROWS")
    hcc={k for k,r in part.items() if r.get("HCC","").strip()=="1"}
    if any(r.get("HCC","").strip() not in ("0","1") for r in part.values()):
        raise ValueError("UNEXPECTED_HCC_CASE_LABEL")
    ven_status={(pid,lesion):st for (pid,lesion,seq),st in recorded.items() if seq=="Venous"}
    subjects=all_subjects
    if len(subjects)!=132:
        raise ValueError("EXPECTED_132_PUBLISHED_SUBJECTS_IN_PARTICIPANTS:"+str(len(subjects)))
    if {p for p,_ in hcc} & {p for p,_ in part if p.startswith("TCGA-")}:
        raise ValueError("SOURCE_COHORT_ID_COLLISION")
    candidate=sorted(k for k in hcc if ven_status.get(k) in MASK_PRESENT)
    status_counts=Counter(ven_status.values())
    if not candidate:raise ValueError("NO_HCC_LESION_WITH_DISTRIBUTED_VENOUS_MASK")
    files=[n for n in (deriv_names or []) if not n.endswith("/") and not n.startswith("__MACOSX/")]
    def matching(pid,lesion,seq,second=False):
        prefix="manual_lesion_annotations_second_reader/" if second else "manual_lesion_annotations/"
        search=("/"+prefix).lower()
        ans=[]
        for n in files:
            low="/"+n.lower()
            if (search not in low or pid.lower() not in low or
                not (low.endswith(".nii.gz") or low.endswith(".nii"))):
                continue
            if not re.search(r"[-_]"+re.escape(lesion.lower())+r"_(seg|mask)",low):
                continue
            if seq=="Venous" and ("phase-venous" not in low and "phase-portal" not in low):
                continue
            ans.append(n)
        return ans
    rows=[]
    for pid,lesion in candidate:
        a=part[(pid,lesion)]
        first=matching(pid,lesion,"Venous")
        second=matching(pid,lesion,"Venous",True)
        if len(first)>1:raise ValueError("AMBIGUOUS_VENOUS_FIRST_READER_MASK:"+pid+":"+lesion)
        if len(second)>1:raise ValueError("AMBIGUOUS_VENOUS_SECOND_READER_MASK:"+pid+":"+lesion)
        rows.append({
          "external_source":"OpenSwissHCC_v2_Zenodo_21992461",
          "subject":pid,"lesion":lesion,"HCC_label":a["HCC"],
          "proven_HCC":a.get("Proven HCC",""),
          "venous_lesion_annotation_status":ven_status[(pid,lesion)],
          "study_MRI_machine":a.get("Machine",""),
          "venous_lesion_first_mask_path":first[0] if first else "",
          "venous_lesion_second_mask_path":second[0] if second else "",
          "metadata_eligible": "YES",
          "mask_in_derivative_zip":"NOT_CHECKED" if deriv_names is None else
             "YES" if first else "NO_NEEDS_FILE_MAPPING",
          "MRI_venous_image_downloaded":"NO",
          "image_mask_geometry_verified":"NOT_ASSESSED",
          "external_radiomics_extraction":"NOT_EXECUTED",
          "patient_clinical_RNA_eligibility":"NOT_ASSESSED",
          "claim_ceiling":"S0"
        })
    counts={
       "official_source_record":REC,"version":"v2",
       "patients_with_any_participant_row":len(subjects),
       "lesion_metadata_rows":len(part),
       "control_subjects_with_no_lesion_rows":len(no_lesion_subjects),
       "HCC_labeled_lesion_metadata_rows":len(hcc),
       "HCC_labeled_subjects_with_lesion_rows":len({p for p,_ in hcc}),
       "total_annotation_status_rows":len(recorded),
       "unique_annotated_lesion_pairs":len({(p,l) for p,l,_ in recorded}),
       "venous_status_lesion_pairs":len(ven_status),
       "venous_status_summary":dict(status_counts),
       "HCC_venous_mask_reported_lesions":len(candidate),
       "HCC_venous_mask_reported_subjects":len({p for p,_ in candidate}),
       "derivative_zip_names_inspected":len(files),
       "HCC_venous_first_reader_masks_found":sum(bool(x["venous_lesion_first_mask_path"]) for x in rows),
       "HCC_venous_second_reader_masks_found":sum(bool(x["venous_lesion_second_mask_path"]) for x in rows),
       "images_downloaded":0,"external_radiomics_extractions":0,
       "clinical_eligible_n":"NOT_ASSESSED",
       "MRI_RNA_associations_executed":0,
       "external_validation_claim":"NOT_YET",
       "claim_ceiling":"S0"}
    if deriv_names is not None and len(files)<100:
        raise ValueError("DERIVATIVE_SOURCE_DIRECTORY_UNEXPECTEDLY_EMPTY")
    return counts,rows

def derivatives_index(path):
    data=path.read_bytes()
    if hashlib.md5(data).hexdigest()!=DERIVATIVE_MD5:
        raise ValueError("ZENODO_V2_DERIVATIVES_113MB_MD5_DRIFT")
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError("DUPLICATED_DERIVATIVE_PATHS")
        # Inverted file lists only: do not extract or redistribute masks here.
        if any(".." in Path(x).parts or x.startswith("/") for x in names):
            raise ValueError("ARCHIVE_PATH_TRAVERSAL")
    return names

def write(out,summary,rows):
    out.mkdir(parents=True,exist_ok=True)
    (out/"openswisshcc_v2_external_hcc_venous_access_preflight.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    with (out/"openswisshcc_v2_venous_hcc_mask_candidate_manifest.csv").open(
        "w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print("HCC_EXTERNAL_OPENSWISSHCC_V2_ACTUAL_METADATA_PREFLIGHT",json.dumps({
        k:v for k,v in summary.items() if k.endswith("_rows") or
        "HCC_venous" in k or k in ("patients_with_any_participant_row",
        "unique_annotated_lesion_pairs","lesion_metadata_rows",
        "derivative_zip_names_inspected","claim_ceiling")}),flush=True)

def fixture():
    a=[
      {"ID":"sub-001","Lesion index":"1","HCC":"1","Machine":"Skyra","Proven HCC":"1"},
      {"ID":"sub-002","Lesion index":"2","HCC":"0","Machine":"Skyra","Proven HCC":""}]
    b=[
      {"subject":"sub-001","lesion":"L1","sequence":"Venous","Status":"annotated"},
      {"subject":"sub-002","lesion":"L2","sequence":"Venous","Status":"not_visible"}]
    # Small fixture cannot satisfy the source-specific 132-subject count,
    # which must reject synthetic cohort promotion as "real" 132-person audit.
    try:preflight(a,b)
    except ValueError as ex:
        assert "EXPECTED_132" in str(ex)
    else:raise AssertionError("SYNTHETIC_TWO_PATIENT_COHORT_ACCEPTED")
    b.append(dict(b[0]))
    try:preflight(a,b)
    except ValueError as ex:
        assert "ANNOTATION" in str(ex)
    else:raise AssertionError("DUPLICATE_LESION_SEQUENCE_ACCEPTED")
    print("OPENSWISSHCC_V2_EXTERNAL_SOURCE_FAIL_CLOSED_FIXTURES_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--source-dir",type=Path)
    ap.add_argument("--derivatives-zip",type=Path)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_openswiss_external"))
    args=ap.parse_args()
    if args.offline_test:return fixture()
    if args.source_dir is None:raise ValueError("SMALL_ORIGINAL_ZENODO_METADATA_FILES_REQUIRED")
    pinned_files(args.source_dir)
    names=derivatives_index(args.derivatives_zip) if args.derivatives_zip else None
    meta,rows=preflight(decode(args.source_dir/"participants.tsv"),
                        decode(args.source_dir/"annotation_status.tsv"),names)
    meta["metadata_exact_md5_verified_files"]=PINNED
    meta["derivative_zip_exact_md5_verified"]=DERIVATIVE_MD5 if names else "NOT_CHECKED"
    if names:
        meta["mask_files_exist_for_all_metadata_candidates"]=all(x["venous_lesion_first_mask_path"] for x in rows)
        meta["physical_image_geometry_verified"]=False
        meta["source_eligible_for_external_radiomics"]="PENDING_VENOUS_IMAGE_ACCESS_AND_IMAGE_MASK_GEOMETRY"
    else:meta["source_eligible_for_external_radiomics"]="PENDING_DERIVATIVE_MASK_FILE_CHECK"
    write(args.out_dir,meta,rows)

if __name__=="__main__":main()
