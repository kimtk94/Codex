#!/usr/bin/env python3
"""Freeze n14 actual registered-PV z spacing / GLCM engineering QA evidence.

Original run: https://github.com/kimtk94/Codex/actions/runs/41214675184
Original artifact: 13047649835. Four SHA256-pinned original members.
This is NOT a clinical/biology association discovery.
"""
import argparse,csv,io,hashlib,zipfile,math,statistics,json
from collections import Counter
from pathlib import Path
from mri_phase_mask_source_gate import frozen

PATH=Path("research/hcc/HCC_MRI14_REGPV_EXACT_SPACING_GLCM_STUDY_CONTRAST_FROZEN_20261101.csv")
SOURCE={
"hcc_regpv_12_published_study_contrast_group_descriptives.csv":"b9ce694bed300c9e12a955e4a7fabfe9123c8de3e2847dc22daaffbfc6a1ab6a",
"hcc_regpv_14_patient_exact_spacing_glcm_and_agent.csv":"62ab91506644e789d1ab7db923defd5ceef64fa3659897c72fc4fc2566f0d041",
"hcc_regpv_20_spacing_glcm_spearman_descriptive_loo.csv":"1ac7230dbfc9c5d826550a6f53d634e5e3617fb24431ab17dabb8fbc860b04f2",
"hcc_regpv_acquisition_descriptive_summary.json":"ed4ec8092ad4cc0c9a889175c917633e18233f97b041373fbae8d2861c2f51c5",
}
FIELDS={
"registered_spacing_x_mm":"registered_spacing_x_mm",
"registered_spacing_y_mm":"registered_spacing_y_mm",
"registered_voxel_spacing_z_mm":"registered_voxel_spacing_z_mm",
"historical_raw_pv_z_mm":"historical_raw_pv_z_mm",
"registered_z_inplane_anisotropy_ratio":"registered_z_inplane_anisotropy_ratio",
"published_study_contrast_category":"published_study_contrast_category",
"glcm_3mm25_abs_change_pct":"glcm_3mm25_abs_change_pct",
"glcm_3mm25_signed_change_pct":"glcm_3mm25_signed_change_pct",
}
def read_csv(binary):
    return list(csv.DictReader(io.StringIO(binary.decode("utf8"))))

def cases(rows):
    ids=[r["patient_id"] for r in rows]
    if len(ids)!=14 or len(set(ids))!=14 or set(ids)!=set(frozen()):
        raise ValueError("MISSING_SOURCE_CASES_IN_FROZEN_N14")
    return {r["patient_id"]:r for r in rows}

def close(x,y,tol=1.1e-6):
    try:
        xx,yy=float(x),float(y)
        return math.isfinite(xx) and math.isfinite(yy) and abs(xx-yy)<=tol
    except (ValueError,TypeError):return False

def rank(values):
    data=[float(x) for x in values]
    if not all(map(math.isfinite,data)):raise ValueError("NONFINITE_RANK")
    result=[0.]*len(data)
    order=sorted(range(len(data)),key=lambda i:data[i])
    i=0
    while i<len(order):
        j=i+1
        while j<len(order) and data[order[i]]==data[order[j]]:j+=1
        avg=((i+1)+j)/2
        for idx in order[i:j]:result[idx]=avg
        i=j
    return result

def rho(x,y):
    a,b=rank(x),rank(y)
    ma=sum(a)/len(a);mb=sum(b)/len(b)
    sa=sum((v-ma)**2 for v in a);sb=sum((v-mb)**2 for v in b)
    if sa<1e-12 or sb<1e-12:raise ValueError("DEGENERATE_RANK")
    return sum((v-ma)*(w-mb) for v,w in zip(a,b))/math.sqrt(sa*sb)

def validate_frozen():
    data=cases(read_csv(PATH.read_bytes()))
    if sum(int(r["index_tumor"])!=frozen()[p] for p,r in data.items()):
        raise ValueError("FROZEN_TUMOR_DRIFT")
    cats=Counter(r["published_study_contrast_category"] for r in data.values())
    if cats!={"Extracellular":7,"Hepatobiliary-specific":4,"not avaliable":3}:
        raise ValueError("UNEXPECTED_STUDY_AGENT_GROUPS")
    for p,r in data.items():
        if (r["exact_selected_series_agent_approved"]!="NOT_VERIFIED"
            or r["clinical_eligibility"]!="NOT_ASSESSED" or r["claim_ceiling"]!="S0"):
            raise ValueError("ILLEGAL_CLINICAL_OR_AGENT_SERIES_APPROVAL")
        if not close(r["registered_voxel_spacing_z_mm"],r["historical_raw_pv_z_mm"]):
            raise ValueError("SOURCE_REGISTERED_AND_HISTORICAL_RAW_Z_NOT_NUMERICALLY_EQUAL")
    x=[float(r["registered_voxel_spacing_z_mm"]) for r in data.values()]
    y=[float(r["glcm_3mm25_abs_change_pct"]) for r in data.values()]
    if not close(statistics.median(y),86.59375,1.1e-6):
        raise ValueError("SOURCE_CHANGE_MEDIAN_REFERENCE_DRIFT")
    if not close(rho(x,y),-.419048,1.1e-6):
        raise ValueError("PUBLISHED_ALL14_DESCRIPTIVE_RHO_DRIFT")
    pairs=[(p,r) for p,r in data.items() if p!="TCGA-BC-A10Y"]
    x13=[float(r["registered_voxel_spacing_z_mm"]) for _,r in pairs]
    y13=[float(r["glcm_3mm25_abs_change_pct"]) for _,r in pairs]
    if not close(rho(x13,y13),-.269253,1.1e-6):
        raise ValueError("TECHNICAL_A10Y_FLAG_SENSITIVITY_DRIFT")
    if (data["TCGA-BC-A10Y"]["index_tumor"]!="3" or
        not close(data["TCGA-BC-A10Y"]["registered_voxel_spacing_z_mm"],10.8) or
        not close(data["TCGA-BC-A10Y"]["glcm_3mm25_abs_change_pct"],.328456) or
        not close(data["TCGA-DD-A4NJ"]["glcm_3mm25_abs_change_pct"],251.405522)):
        raise ValueError("ORIGINAL_EXTREME_PATIENT_VALUES_DRIFT")
    return data

def verify_artifact(zippath,reference):
    with zipfile.ZipFile(zippath) as z:
        if set(z.namelist())!=set(SOURCE):
            raise ValueError("EXACT_4_ORIGINAL_ARTIFACT_MEMBERS_REQUIRED")
        parts={n:z.read(n) for n in SOURCE}
    for n,digest in SOURCE.items():
        if hashlib.sha256(parts[n]).hexdigest()!=digest:
            raise ValueError("SHA256_SOURCE_ARTIFACT_CHANGED:"+n)
    full=cases(read_csv(parts["hcc_regpv_14_patient_exact_spacing_glcm_and_agent.csv"]))
    reports=read_csv(parts["hcc_regpv_20_spacing_glcm_spearman_descriptive_loo.csv"])
    agent=read_csv(parts["hcc_regpv_12_published_study_contrast_group_descriptives.csv"])
    summary=json.loads(parts["hcc_regpv_acquisition_descriptive_summary.json"])
    if len(reports)!=20 or len(agent)!=12 or summary["n_exact_official_art_pv_source_headers"]!=14:
        raise ValueError("ORIGINAL_20_DESCRIPTIVE_12_AGENT_COUNTS_CHANGED")
    if (summary["MRI_RNA_12_tests"]!="NOT_EXECUTED" or summary["claim_ceiling"]!="S0"
        or summary["clinical_eligibility"]!="NOT_ASSESSED"
        or summary["scanner_vendor_for_exact_pv_series"]!="NOT_VERIFIED"
        or summary["contrast_agent_for_exact_pv_series"]!="NOT_VERIFIED"):
        raise ValueError("BIOLOGICAL_OR_AGENT_CLAIM_CHANGED")
    for pid,expected in reference.items():
        original=full[pid]
        for k in FIELDS:
            if k=="published_study_contrast_category":
                if original[k]!=expected[k]:
                    raise ValueError("STUDY_AGENT_RECLASSIFIED:"+pid)
            elif not close(original[k],expected[k]):
                raise ValueError("CASE_LEVEL_OFFICIAL_SPACING_GLCM_CHANGED:"+pid+":"+k)
        if original["MRI_RNA_association_tests"]!="NOT_EXECUTED" or original["claim_ceiling"]!="S0":
            raise ValueError("SCIENTIFIC_BIOLOGY_PROMOTION_IN_SOURCE_OUTPUT")
    main=next(r for r in reports if r["covariate"]=="registered_voxel_spacing_z_mm" and
              r["descriptive_feature_change"]=="glcm_3mm25_abs_change_pct")
    if (not close(main["spearman_rho"],-.419048)
        or not close(main["leave_one_patient_out_max_rho"],-.269253)
        or not close(main["leave_one_patient_out_min_rho"],-.530801)):
        raise ValueError("SOURCE_LOO_RANK_DRIFT")
    groups={}
    for r in agent:
        if r["feature_change"]=="glcm_3mm25_abs_change_pct":
            groups[r["published_study_contrast_category"]]=(int(r["n"]),float(r["median_change_pct"]))
    for group,n,median in [("Extracellular",7,87.959779),
          ("Hepatobiliary-specific",4,114.837127),
          ("not avaliable",3,70.381267)]:
        if group not in groups or groups[group][0]!=n or not close(groups[group][1],median):
            raise ValueError("STUDY_AGENT_GROUP_REFERENCE_DRIFT")
    return True

def fixture():
    data=validate_frozen()
    assert len(data)==14
    assert close(rho([1,2,3,4],[4,3,2,1]),-1)
    assert close(rho([1,2,2,4],[1,2,2,4]),1)
    assert data["TCGA-DD-A4NJ"]["clinical_eligibility"]=="NOT_ASSESSED"
    print("HCC_MRI14_REGPV_ACQUISITION_FROZEN_14_CASE_SOURCE_AND_S0_GUARD_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-zip",type=Path)
    args=ap.parse_args()
    if args.source_zip is None:return fixture()
    data=validate_frozen()
    verify_artifact(args.source_zip,data)
    print("HCC_MRI14_REGPV_SOURCE_4_SHA_14_PATIENT_20_LOO_12_AGENT_S0_PASS")
if __name__=="__main__":main()
