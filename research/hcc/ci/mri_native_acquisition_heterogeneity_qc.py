#!/usr/bin/env python3
"""Source-verified LiverHccSeg MRI acquisition heterogeneity QC, 14 cases.

Uses official checksum-pinned MRI metadata workbook (13 KiB), plus frozen
original PV MRI voxel spacing extracted from BOTH PyRadiomics rater profiles.
Never reads/export StudyDate (TCIA shifted), never imputes scanner vendor, and
does not imply workbook patient-level field strength belongs to exact PV series.

Outputs only acquisition protocol risk flags; no MRI/RNA association tests.
"""
import argparse,csv,json,math,re,statistics
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from liverhccseg_mri_rna_audit import FILES,fetch_workbook
from mri_parallel_batch_gate import ROI,load

SPACING="research/hcc/HCC_MRI_14_PV_NATIVE_SPACING_QC_20261031.csv"
FIELDS=("patient_id","selected_tumor_number","voxel_spacing_x_mm",
"voxel_spacing_y_mm","voxel_spacing_z_mm","z_to_inplane_ratio",
"native_spacing_flag","official_metadata_rows",
"study_field_strength_values_t","study_field_strength_status",
"published_contrast_agent_labels","published_contrast_agent_types",
"exact_PV_series_magnetic_field_strength","scanner_manufacturer",
"scanner_model","dicom_sequence_parameters",
"metadata_to_exact_PV_series_link","selected_index_tumor_review",
"patient_mri_pretreatment","final_clinical_eligibility")

def header_norm(x):
    return re.sub(r"[^a-z0-9]","",str(x or "").lower())

def parse_field_strength(x):
    if x is None or isinstance(x,bool):return None
    s=str(x).replace(",",".").strip().lower()
    if not s or s in ("not available","not reported","na","none","nan","0"):return None
    # Parse only plausible 1.5T or 3T values with optional Tesla suffix.
    if re.fullmatch(r"1\.5\s*(?:t|tesla)?",s):return 1.5
    if re.fullmatch(r"3(?:\.0)?\s*(?:t|tesla)?",s):return 3.0
    return None

def parse_book(wb,subjects):
    values=defaultdict(list)
    source_headers=[]
    for sheet in wb.worksheets:
        iterator=sheet.iter_rows(values_only=True)
        first=next(iterator,())
        headers={header_norm(v):i for i,v in enumerate(first)}
        source_headers.append({"sheet":sheet.title,"raw_headers":[str(x or "") for x in first]})
        if "patientid" not in headers:
            continue
        index=headers["patientid"]
        field=headers.get("magneticfieldstrength")
        agent=headers.get("contrastagent")
        agent_type=headers.get("contrastagenttype")
        for row in iterator:
            if index>=len(row):continue
            s=str(row[index] or "").replace("_","-").upper().strip()
            m=re.search(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}",s)
            if m is None or m.group(0) not in subjects:continue
            pid=m.group(0)
            def get(i):
                if i is None or i>=len(row):return ""
                return str(row[i]).strip() if row[i] is not None else ""
            values[pid].append({
                "field_strength_raw":get(field),
                "contrast_agent":get(agent),
                "contrast_agent_type":get(agent_type),
            })
    return values,source_headers

def audit(spacing,roi,metadata):
    if set(spacing)!=set(roi) or set(roi)!=set(metadata):
        raise ValueError("Official MRI acquisition / PV native spacing / ROI patient sets disagree")
    rows=[]
    for pid in sorted(roi):
        r,s=roi[pid],spacing[pid]
        if (s["selected_tumor_number"]!=r["representative_tumor_number"]
          or s["source_phase"]!="PV"
          or s["rater2_source_geometry_match"]!="YES"
          or s["extractor_version"]!="v3.1.0"
          or s["clinical_eligibility"]!="NOT_ASSESSED"):
            raise ValueError("PV spacing traceability, rater or clinic label drift")
        x,y,z=[float(s[k]) for k in ("voxel_spacing_x_mm","voxel_spacing_y_mm","voxel_spacing_z_mm")]
        ratio=z/((x+y)/2)
        if any(not math.isfinite(a) or a<=0 for a in (x,y,z)) or abs(ratio-float(s["z_to_inplane_ratio"]))>1e-4:
            raise ValueError("Original PV MRI native NIfTI spacing invalid or ratio drift")
        flag=("HIGH_THROUGHPLANE_ANISOTROPY_REVIEW" if z>=5.0 or ratio>=4.0
              else "NONISOTROPIC_NATIVE_MRI_REVIEW")
        info=metadata[pid]
        if not info:raise ValueError("No official source metadata rows")
        strengths=sorted({q for v in info if (q:=parse_field_strength(v["field_strength_raw"])) is not None})
        unparsed=sorted({v["field_strength_raw"] for v in info
                         if v["field_strength_raw"] and parse_field_strength(v["field_strength_raw"]) is None})
        strength_status=(
            "DIFFERENT_FIELD_STRENGTHS_IN_PATIENT_METADATA" if len(strengths)>1
            else "PUBLISHED_PATIENT_LEVEL_FIELD_STRENGTH_NOT_PV_SERIES" if strengths and not unparsed
            else "MISSING_OR_UNRECOGNIZED_FIELD_STRENGTH_REVIEW")
        rows.append({
            "patient_id":pid,
            "selected_tumor_number":s["selected_tumor_number"],
            "voxel_spacing_x_mm":x,"voxel_spacing_y_mm":y,"voxel_spacing_z_mm":z,
            "z_to_inplane_ratio":round(ratio,5),
            "native_spacing_flag":flag,
            "official_metadata_rows":len(info),
            "study_field_strength_values_t":"|".join(str(q) for q in strengths),
            "study_field_strength_status":strength_status,
            "published_contrast_agent_labels":"|".join(sorted(set(
                x["contrast_agent"] for x in info if x["contrast_agent"]))),
            "published_contrast_agent_types":"|".join(sorted(set(
                x["contrast_agent_type"] for x in info if x["contrast_agent_type"]))),
            "exact_PV_series_magnetic_field_strength":"NOT_VERIFIED",
            "scanner_manufacturer":"NOT_REPORTED_IN_THIS_WORKBOOK",
            "scanner_model":"NOT_REPORTED_IN_THIS_WORKBOOK",
            "dicom_sequence_parameters":"NOT_VERIFIED",
            "metadata_to_exact_PV_series_link":"NOT_VERIFIED",
            "selected_index_tumor_review":"NOT_ASSESSED",
            "patient_mri_pretreatment":"NOT_VERIFIED",
            "final_clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
        })
    return rows

def summarize(rows,metadata_headers,hashinfo):
    n_hi=[r for r in rows if r["native_spacing_flag"]=="HIGH_THROUGHPLANE_ANISOTROPY_REVIEW"]
    zs=[float(r["voxel_spacing_z_mm"]) for r in rows]
    ratios=[float(r["z_to_inplane_ratio"]) for r in rows]
    strength=Counter()
    for r in rows:
        if r["study_field_strength_values_t"]:
            for x in r["study_field_strength_values_t"].split("|"):strength[x]+=1
        else:strength["UNKNOWN"]+=1
    return {
       "status":"PASS_MRI_NATIVE_RESOLUTION_AND_PATIENT_METADATA_QC_ONLY",
       "checked_utc":datetime.now(timezone.utc).isoformat(),
       "official_zenodo_record":"8179129",
       "official_source_md5":hashinfo,
       "source_column_availability":{
           "has_patient_id":any("patientid" in (header_norm(x) for x in h["raw_headers"]) for h in metadata_headers),
           "has_magnetic_field_strength":any("magneticfieldstrength" in (header_norm(x) for x in h["raw_headers"]) for h in metadata_headers),
           "has_scanner_manufacturer":any("manufacturerscanner" in (header_norm(x) for x in h["raw_headers"]) for h in metadata_headers),
           "has_study_date":any("studydate" in (header_norm(x) for x in h["raw_headers"]) for h in metadata_headers),
       },
       "candidates":len(rows),
       "official_metadata_present":sum(int(r["official_metadata_rows"])>0 for r in rows),
       "high_throughplane_anisotropy_patients":[r["patient_id"] for r in n_hi],
       "high_throughplane_anisotropy_count":len(n_hi),
       "native_slice_thickness_mm_min":min(zs),
       "native_slice_thickness_mm_median":statistics.median(zs),
       "native_slice_thickness_mm_max":max(zs),
       "native_ratio_min":min(ratios),
       "native_ratio_max":max(ratios),
       "patient_level_magnetic_field_strength_counts":dict(strength),
       "exact_PV_series_acquisition_provenance_verified":0,
       "predeclared_radiomics_feature_sensitivity_required":True,
       "scanner_vendor_unknown_is_not_same_vendor":True,
       "published_patient_mri_pretreatment_verified":0,
       "imaging_rna_association_tests":0,
       "clinical_eligibility":"NOT_ASSESSED",
       "claim_ceiling":"S0",
       "caveats":[
           "Original PV native NIfTI spacing is actual image geometry; official workbook magnetic strength may refer to a study, not the selected PV series.",
           "No StudyDate, shifted DICOM relative date, or raw patient age/sex exported.",
           "Contrast agent manufacturer is NOT scanner manufacturer.",
           "A10Y original PV thick slices merit preplanned texture resampling sensitivity; do not post hoc delete the case based on association p-values.",
           "No ComBat harmonization or scanner feature adjustment can be justified from incomplete scanner/phase metadata and n=14."
       ]
    }

def offline_test():
    roi=load(ROI)
    sp=load(SPACING)
    fake={pid:[{"field_strength_raw":"3.0 T","contrast_agent":"Gd",
               "contrast_agent_type":""}] for pid in roi}
    rows=audit(sp,roi,fake)
    assert len(rows)==14
    hi=[x["patient_id"] for x in rows if x["native_spacing_flag"]=="HIGH_THROUGHPLANE_ANISOTROPY_REVIEW"]
    assert hi==["TCGA-BC-A10Y"],hi
    assert abs(next(x["z_to_inplane_ratio"] for x in rows if x["patient_id"]=="TCGA-BC-A10Y")-14.55133)<1e-4
    assert all(x["exact_PV_series_magnetic_field_strength"]=="NOT_VERIFIED" for x in rows)
    assert parse_field_strength("1.5T")==1.5
    assert parse_field_strength("3.0 T")==3.0
    assert parse_field_strength("Siemens")==None
    fake["TCGA-BC-A10Y"]=[]
    try:audit(sp,roi,fake)
    except ValueError:pass
    else:raise AssertionError("Missing MRI patient metadata must block audit")
    print("HCC_MRI_OFFICIAL_ACQUISITION_AND_NATIVE_SPACING_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_batch_acquisition")
    args=p.parse_args()
    if args.offline_test:return offline_test()
    roi=load(ROI);spacing=load(SPACING)
    filename="LiverHccSeg_MetaData.xlsx"
    wb,digest,nbytes=fetch_workbook(filename,FILES[filename])
    try:
        metadata,headers=parse_book(wb,set(roi))
    finally:wb.close()
    rows=audit(spacing,roi,metadata)
    summary=summarize(rows,headers,{"file":filename,"md5":digest,"bytes":nbytes})
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/"hcc_mri14_acquisition_native_spacing_qc.csv").open(
            "w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (out/"hcc_mri14_acquisition_heterogeneity_summary.json").write_text(
            json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if summary["official_metadata_present"]!=14:raise SystemExit(1)

if __name__=="__main__":
    main()
