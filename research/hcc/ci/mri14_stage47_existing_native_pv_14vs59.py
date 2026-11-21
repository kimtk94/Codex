#!/usr/bin/env python3
"""HCC Stage47 SOURCE-ONLY, zero image downloads: 14 native-PV reader1 versus
59 external original native venous patients, both native bw25 -> 3mm bw25.

IMPORTANT: this compares per-patient *descriptive processing sensitivity*
measures in different cohorts, NOT same scanner, not inter-reader repeatability,
not test-retest, not formally exchangeable treatment effects. The rater1
source is a deliberate single-reader sensitivity arm, not a prospectively
defined primary MRI-RNA endpoint. All source images/ROIs originated in
previous verified Actions and permanent frozen CSV tables.
"""
import argparse,csv,json,math,os,random,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INTERNAL=ROOT/"HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv"
INTERNAL_READER_SUMMARY=ROOT/"HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv"
INTERNAL_REPORT=ROOT/"HCC_MRI_PV_14_NATIVE_VS_3MM_SENSITIVITY_REPORT_20261031.md"
EXTERNAL=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv"
EXTERNAL_CI=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_24_CONDITION_BOOTSTRAP_FROZEN_20261101.csv"
SCRIPT_VERSION="HCC47_original_native_rater1_external59_v1"
FIELDS=("cohort","patient_id","index_lesion","mask_reader","source_measurement",
        "native_to_3mm_bw25_glcm_contrast_absolute_change_pct",
        "original_slice_spacing_mm","source_run","clinical_eligible",
        "MRI_RNA_tests","claim_ceiling")

def ensure(ok,label):
    if not ok:raise ValueError(label)

def csvrows(path):
    ensure(path.is_file(),"FROZEN_SOURCE_CSV_MISSING:"+str(path))
    with path.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def bootmedian(values,seed=20261102,niter=4000):
    rng=random.Random(seed)
    n=len(values)
    arr=sorted(statistics.median(values[rng.randrange(n)] for _ in range(n))
               for _ in range(niter))
    return [arr[int((niter-1)*.025)],arr[int((niter-1)*.975)]]

def run():
    a=csvrows(INTERNAL)
    b=csvrows(EXTERNAL)
    icc=csvrows(INTERNAL_READER_SUMMARY)
    external_ci=csvrows(EXTERNAL_CI)
    ensure(len(a)==14 and len({x["patient_id"] for x in a})==14,
           "FROZEN_NATIVE_TCGALIHC_14_CASES_DRIFT")
    ensure(len(b)==59 and len({x["subject"] for x in b})==59,
           "FROZEN_NATIVE_OPENSWISS_59_CASES_DRIFT")
    ensure(len(icc)==10 and len(external_ci)==24,
           "FROZEN_SOURCE_FEATURE_SUMMARY_UNIVERSE_CHANGED")
    ensure(all(x["patient_id"].startswith("TCGA-") and
               x["clinical_eligibility"]=="HOLD_UNRESOLVED_NOT_EXCLUDED" and
               int(x["tumor_number"])>=1 for x in a),
           "FROZEN_TCGALIHC_INDEX_LESION_OR_HOLD_DRIFT")
    ensure(all(x["subject"].startswith("sub-") and
               x["claim_ceiling"]=="S0" and
               x["original_source_run"]=="41221356861" for x in b),
           "FROZEN_EXTERNAL_ORIGINAL_SOURCE_HOLD_DRIFT")
    ensure("normalization" in INTERNAL_REPORT.read_text() and
           "B-spline" in INTERNAL_REPORT.read_text() and
           "binWidth=25" in INTERNAL_REPORT.read_text(),
           "NATIVE_INTERNAL_EXACT_PREPROCESSING_REPORT_NOT_PRESENT")
    rc=[x for x in icc if x["feature"]=="original_glcm_Contrast"]
    ensure(len(rc)==1 and abs(float(rc[0]["native_to_3mm_median_absolute_relative_change"])*100-77.0667)<.02,
           "INTERNAL_TWO_RATER_SOURCE_GLCM_MEDIAN_DRIFT")
    ref=[x for x in external_ci if x["feature"]=="original_glcm_Contrast" and x["grid"]=="3mm" and x["binWidth"]=="25"]
    ensure(len(ref)==1,"EXTERNAL_GLCM_SOURCE_REFERENCE_NOT_UNIQUE")
    rows=[]; internal_values=[];external_values=[]
    for x in sorted(a,key=lambda z:z["patient_id"]):
        change=float(x["glcm_contrast_rater1_absolute_relative_change"])*100
        z=float(x["native_z_mm"])
        ensure(math.isfinite(change) and change>=0 and math.isfinite(z) and z>0,
               "INTERNAL_NATIVE_PV_RATER1_SOURCE_NONFINITE")
        internal_values.append(change)
        rows.append(dict(cohort="TCGA_LIHC_LiverHccSeg_native_PV",
          patient_id=x["patient_id"],index_lesion="tumor"+x["tumor_number"],
          mask_reader="rater1",source_measurement="NATIVE_PV_BW25_TO_3MM_BW25",
          native_to_3mm_bw25_glcm_contrast_absolute_change_pct=round(change,6),
          original_slice_spacing_mm=z,source_run=41161863748,
          clinical_eligible="NOT_ASSESSED",MRI_RNA_tests=0,claim_ceiling="S0"))
    for x in sorted(b,key=lambda z:z["subject"]):
        native=float(x["original_native25_GLCM_Contrast"])
        interp=float(x["resampled_3mm25_GLCM_Contrast"])
        change=abs((interp-native)/native)*100
        ensure(native>0 and interp>0 and
               abs(change-abs(float(x["signed_change_pct"])))<.002,
               "EXTERNAL_GLCM_N59_RECALCULATION_MISMATCH")
        spacing=[float(v) for v in x["source_voxel_spacing_xyz_mm"].split("|")]
        ensure(len(spacing)==3 and all(math.isfinite(v) and v>0 for v in spacing),
               "EXTERNAL_ORIGINAL_IMAGE_NATIVE_SPACING_MISSING")
        external_values.append(change)
        rows.append(dict(cohort="OpenSwissHCC_v2_original_venous",
          patient_id=x["subject"],index_lesion=x["selected_HCC_lesion"],
          mask_reader="original_source_primary",source_measurement="NATIVE_PV_BW25_TO_3MM_BW25",
          native_to_3mm_bw25_glcm_contrast_absolute_change_pct=round(change,6),
          original_slice_spacing_mm=spacing[2],source_run=41221356861,
          clinical_eligible="NOT_ASSESSED",MRI_RNA_tests=0,claim_ceiling="S0"))
    med14=statistics.median(internal_values)
    med59=statistics.median(external_values)
    ensure(abs(med14-74.8808)<.005,"N14_NATIVE_RATER1_SOURCE_MEDIAN_CHANGED")
    ensure(abs(med59-64.635863)<.002,"N59_NATIVE_PRIMARY_SOURCE_MEDIAN_CHANGED")
    ci14=bootmedian(internal_values)
    loo14=[statistics.median([v for j,v in enumerate(internal_values) if j!=i])
           for i in range(14)]
    loo59=[statistics.median([v for j,v in enumerate(external_values) if j!=i])
           for i in range(59)]
    summary=dict(
        stage=SCRIPT_VERSION,
        original_source_cohort_internal_n=14,
        independent_source_cohort_external_n=59,
        source_one_lesion_one_patient_per_cohort=True,
        original_PV_native25_3mm25_physical_perturbation_nominally_shared=True,
        exact_MRI_acquisition_scanner_or_segmentation_protocol_equivalence=False,
        no_new_source_image_download_or_feature_extraction=True,
        internal_tcgaliHC_native_pv_rater1_median_abs_change_pct=med14,
        internal_tcgaliHC_native_pv_rater1_bootstrap95_exploratory_pct=ci14,
        internal_tcgaliHC_native_pv_rater1_loo_median_range_pct=[min(loo14),max(loo14)],
        internal_tcgaliHC_all_two_rater_source_median_abs_change_pct=77.0667,
        external_openswiss_native_pv_rater1_median_abs_change_pct=med59,
        external_openswiss_native_pv_4000_bootstrap95_frozen_pct=[
          float(ref[0]["bootstrap95_low"]),float(ref[0]["bootstrap95_high"])],
        external_openswiss_loo_median_range_pct=[min(loo59),max(loo59)],
        between_cohort_descriptive_median_difference_percentage_points=med14-med59,
        between_cohort_difference_formal_test_performed=False,
        paired_test_retest_or_intervention_performed=False,
        source_ICC14_rater_pairs_exist=14,
        external_second_reader_index_lesion_pairs_exist=3,
        clinical_eligible_n="NOT_ASSESSED",MRI_RNA_biological_tests=0,
        clinical_biological_claim_ceiling="S0",
        methodological_thesis_status="CONDITIONAL_GO_REQUIRES_EXPERT_ROI_NOVELTY_AND_PROTOCOL_REVIEW",
        interpretation="WITHIN_EACH_COHORT_PROCESSING_SENSITIVITY_ONLY_NO_CROSS_COHORT_CAUSALITY")
    ensure(len(rows)==73 and
           len({(r["cohort"],r["patient_id"]) for r in rows})==73,
           "STAGE47_FROZEN_73_UNIQUE_SOURCE_IDS_DRIFT")
    return rows,summary

def output(root,rows,summary):
    root.mkdir(parents=True,exist_ok=True)
    with (root/"stage47_nativePV_14rater1_59original_perpatient_sensitivity.csv").open(
        "w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (root/"stage47_14vs59_native_originalPV_descriptive_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n",encoding="utf8")
    md=[
      "# HCC Stage47 existing 14 native PV and independent 59 native venous source matched-measurement audit",
      "",
      "**Both cohorts already had original native-PV→3mm/binWidth25 extracted; NO original image rerun required.**",
      "- Internal TCGA-LIHC n14, one selected original native-PV index-lesion rater1 mask per patient, median absolute GLCM Contrast change **"+
       f'{summary["internal_tcgaliHC_native_pv_rater1_median_abs_change_pct"]:.3f}'+"%**.",
      "- Original n14 all 28 reader-records median change **77.067%**: a different denominator than the n14 rater1-only patient result.",
      "- External OpenSwissHCC n59 independent original venous primary index lesions, median absolute change **"+
       f'{summary["external_openswiss_native_pv_rater1_median_abs_change_pct"]:.3f}'+"%**.",
      "- Exploratory 4,000-draw n14 patient bootstrap interval: "+
       str(summary["internal_tcgaliHC_native_pv_rater1_bootstrap95_exploratory_pct"])+".",
      "- Frozen external n59 4k-bootstrap interval: "+
       str(summary["external_openswiss_native_pv_4000_bootstrap95_frozen_pct"])+".",
      "- Observed median difference, internal minus external, **"+
       f'{summary["between_cohort_descriptive_median_difference_percentage_points"]:.3f}'+" percentage points**; NO formal cohort comparison tested.",
      "- The same nominal MRI intensity binning/resampling contrast was used but scanner, slice thickness, segmentation and source design differ.",
      "- Does not show same numerical *treatment effect* across sites, scanner causality or test–retest scan reliability.",
      "- Original MRI–GDC RNA index-lesion and pretreatment clinical gates HOLD, biology 0/12, S0.",
    ]
    report="\n".join(md)+"\n"
    (root/"stage47_existing_nativePV_sources_preflight_report.md").write_text(report,encoding="utf8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE47_NATIVE_PV_EXISTING14_59_DESCRIPTIVE_SOURCE_AUDIT",
          json.dumps(summary,sort_keys=True),flush=True)
def offline():
    ensure(statistics.median([2,4,6,8])==5,"SOURCE_MEDIAN_TEST")
    ensure(len(bootmedian([2,3,4],niter=20))==2,"SOURCE_BOOTSTRAP_FIXTURE")
    print("HCC_STAGE47_NATIVE_PV_FROZEN_TWO_COHORT_NEGATIVE_FIXTURES_PASS")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage47_native_pv_14_59"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    offline()
    if a.offline_test:return
    output(a.out_dir,*run())
if __name__=="__main__":main()
