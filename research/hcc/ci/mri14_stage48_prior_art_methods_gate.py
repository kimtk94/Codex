#!/usr/bin/env python3
"""Stage48: evidence-bound MSc thesis prior-art / novelty and protocol claim audit.

The literature table is manually curated FROM publisher/PubMed primary abstracts
and keyed by DOI/URL. Optional Crossref calls verify bibliographic metadata only;
they do NOT validate scientific assertions or conduct an exhaustive review.
Stage47 original native-PV n14 and n59 patient-level data are frozen from actual
GitHub Actions. This post-results analysis plan MUST NEVER be called
prospectively preregistered or "new biological validation".
"""
import argparse,csv,json,os,urllib.request,urllib.error,urllib.parse,datetime,time,math
from collections import Counter
from pathlib import Path

ID="HCC_STAGE48_DIRECT_PRIOR_ART_AND_METHODS_CLAIM_AUDIT"
LITERATURE=[
 dict(id="HCC_MRI_PRECISION_2022",year=2022,doi="10.1007/s00330-021-08282-1",
      short="Carbonell et al. European Radiology 2022",
      expected_title_term="precision of mri radiomics features",
      source_url="https://pubmed.ncbi.nlm.nih.gov/34564745/",
      disease="HCC_LIVER_MRI", population="55 MRI patients; 16 untreated HCC",
      validated_scope="MRI same-system test-retest, inter-platform and inter-observer ICC/CCC/CV",
      overlap="CRITICAL: HCC MRI radiomics reproducibility already studied",
      distinction="No actual repeated scan or cross-platform reliability in current frozen two-cohort data",
      novelty_risk="HIGH"),
 dict(id="MRI_VOXEL_BW_2024",year=2024,doi="10.4274/dir.2023.232543",
      short="Kocak et al. Diagnostic and Interventional Radiology 2024",
      expected_title_term="influence of image preprocessing on the segmentation",
      source_url="https://pubmed.ncbi.nlm.nih.gov/38073244/",
      disease="GLIOMA_MRI",population="50 patients; two MRI sequences and multiple raters",
      validated_scope="Voxel resampling, gray-level discretization and segmentation ICC stability",
      overlap="CRITICAL: resampling and bin-width reproducibility comparison not new",
      distinction="Different disease from HCC and stability estimand primarily reader ICC",
      novelty_risk="HIGH"),
 dict(id="HCC_MRI_RESAMPLE_3MM_2023",year=2023,doi="10.1002/jmri.28725",
      short="Cao et al. Journal of Magnetic Resonance Imaging 2023",
      expected_title_term="a cox nomogram for assessing recurrence",
      source_url="https://onlinelibrary.wiley.com/doi/10.1002/jmri.28725",
      disease="HCC_MRI",population="HCC surgical recurrence model cohort",
      validated_scope="Already used 3x3x3 mm B-spline resampling in HCC MRI radiomics pipeline",
      overlap="CRITICAL: 3mm voxel choice itself is clearly not a novel method",
      distinction="Prediction/prognostic model, NOT same within-image patient-rank-vs-magnitude perturbation endpoint",
      novelty_risk="HIGH"),
 dict(id="IBSI_1_2020",year=2020,doi="10.1148/radiol.2020191145",
      short="Zwanenburg et al. Radiology 2020 IBSI",
      expected_title_term="image biomarker standardization initiative",
      source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC7193906/",
      disease="RADIOMICS_STANDARD",population="phantom and clinical images; multiple software teams",
      validated_scope="Standardized radiomics feature definition, source phantom benchmarking and processing",
      overlap="Standardization and IBSI checking are mandatory QC, not novel findings",
      distinction="Current work applies prior standards to lesion-locked original HCC venous MRI cohorts",
      novelty_risk="HIGH"),
 dict(id="ESR_PRACTICE_2025",year=2025,doi="10.1007/s00330-024-11093-9",
      short="Santinha et al. European Radiology 2025 ESR Essentials",
      expected_title_term="esr essentials: radiomics",
      source_url="https://link.springer.com/article/10.1007/s00330-024-11093-9",
      disease="RADIOMICS_GUIDANCE",population="European expert practice guidelines",
      validated_scope="Document image/resampling, binning and validation; avoid workflow leakage",
      overlap="Detailed preprocessing reporting and uncertainty management required",
      distinction="This thesis is a limited observational methods sensitivity comparison",
      novelty_risk="STANDARD_OF_CARE"),
 dict(id="OPENSWISSHCC_DATA_2026",year=2026,doi="10.1038/s41597-026-08506-3",
      short="OpenSwissHCC dataset paper Scientific Data 2026",
      expected_title_term="a multiparametric liver mri dataset",
      source_url="https://www.nature.com/articles/s41597-026-08506-3",
      disease="HCC_MRI_DATA",population="132 MRI subjects; 63 HCC-labeled; 140 lesions",
      validated_scope="Annotated multiphasic MRI collection and tumor masks; not a validation of all our results",
      overlap="Using this public dataset does not itself establish methodological novelty",
      distinction="Current source-locked 59 HCC venous index cases measured native-to-3mm perturbation",
      novelty_risk="MEDIUM")
]
CLAIMS=[
 dict(claim="A novel first-ever HCC MRI radiomics reproducibility study",
      decision="PROHIBITED",reason="Carbonell 2022 already performed real HCC MRI precision testing"),
 dict(claim="3mm isotropic resampling is a new HCC MRI method",
      decision="PROHIBITED",reason="Cao 2023 already used 3x3x3mm B-spline for HCC MRI"),
 dict(claim="MRI preprocessing sensitivity and bin width have not been explored",
      decision="PROHIBITED",reason="Kocak 2024 and IBSI/ESR earlier studies cover this"),
 dict(claim="Within-image native PV to 3mm GLCM magnitude changes observed in two HCC MRI datasets",
      decision="SOURCE_SUPPORTED_DESCRIPTIVE",reason="Stage47 14 and 59 patient-original source data; distinct acquisition protocols"),
 dict(claim="Original external patient ordering preserved despite magnitude changes",
      decision="SOURCE_SUPPORTED_DESCRIPTIVE",reason="Stage46 external n59 paired Spearman 0.940795"),
 dict(claim="Exact dual-cohort effect replicates across scanners",
      decision="PROHIBITED",reason="Different scanner/protocol/ROI conditions and no formal equivalence test"),
 dict(claim="Data were prospectively preregistered before observing results",
      decision="PROHIBITED",reason="The present methods SAP was written AFTER source results inspected"),
 dict(claim="Clinical utility, predictive accuracy, survival or HCC therapy benefit",
      decision="PROHIBITED",reason="No qualified clinical outcome or performance validation"),
 dict(claim="Same MRI index lesion is the sampled RNA tumor and scan predates HCC therapy",
      decision="PROHIBITED",reason="Stage44-45 source clinical pairing remains NOT_ASSESSED"),
 dict(claim="Our current analysis uses genuine independent repeat MRI acquisitions",
      decision="PROHIBITED",reason="Resampling of a single scan is not test-retest"),
 dict(claim="All 59 external masks were independently checked by a new radiologist",
      decision="PROHIBITED",reason="Only 3 frozen external index lesions have second-reader masks; new independent anatomy review absent"),
 dict(claim="A methods-oriented MSc thesis is submission-ready",
      decision="HOLD",reason="Novelty full-methods review, anatomist adjudication and matched patient rank metrics remain pending"),
]
def require(v,label):
    if not v:raise ValueError(label)
def records(path):
    require(path.is_file(),"FROZEN_SOURCE_ARTIFACT_MISSING:"+str(path))
    with path.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))
def citation_metadata_online(dois):
    results=[]
    for x in dois:
        doi=x["doi"]
        url="https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="/")
        status="NOT_VERIFIED_LIVE";title="";year=None;error=""
        for attempt in range(2):
            try:
                req=urllib.request.Request(url,headers={
                    "User-Agent":"HCCStage48-MSc-literature-bibliographic-QC/1.0 (GitHub-Action)",
                    "Accept":"application/json"})
                with urllib.request.urlopen(req,timeout=16) as r:
                    raw=r.read(1024*1024)
                obj=json.loads(raw)["message"]
                title=" ".join(obj.get("title") or [])
                published=obj.get("published",{}) or obj.get("issued",{})
                parts=published.get("date-parts",[]) if published else []
                year=int(parts[0][0]) if parts and parts[0] else None
                actual=obj.get("DOI","").lower()
                term=x["expected_title_term"]
                norm=lambda s:" ".join(s.lower().replace("–","-").split())
                if actual==doi.lower() and term in norm(title) and year and abs(year-x["year"])<=1:
                    status="LIVE_CROSSREF_DOI_TITLE_YEAR_PASS"
                else:status="LIVE_CROSSREF_METADATA_REVIEW"
                break
            except (OSError,TimeoutError,ValueError,KeyError,TypeError) as e:
                error=type(e).__name__+":"+str(e)[:200]
                if attempt==0:time.sleep(0.5)
        results.append(dict(id=x["id"],doi=doi,source_url=url,
           metadata_status=status,returned_title=title,returned_year=year,
           error=error))
        print("HCC_STAGE48_CROSSREF_METADATA_AUDIT",x["id"],status,flush=True)
    return results
def assess(rows,summary):
    require(len(rows)==73 and len({(x["cohort"],x["patient_id"]) for x in rows})==73,
            "STAGE47_PATIENT_DENOMINATOR_NOT_14_PLUS59")
    require(int(summary["original_source_cohort_internal_n"])==14 and
            int(summary["independent_source_cohort_external_n"])==59,
            "STAGE47_FROZEN_SOURCE_COHORT_DRIFT")
    groups=Counter(x["cohort"] for x in rows)
    require(groups=={"TCGA_LIHC_LiverHccSeg_native_PV":14,
                     "OpenSwissHCC_v2_original_venous":59},
            "STAGE47_COHORT_LABELS_OR_COUNTS_CHANGED")
    require(all(x["source_measurement"]=="NATIVE_PV_BW25_TO_3MM_BW25"
                and x["clinical_eligible"]=="NOT_ASSESSED"
                and x["MRI_RNA_tests"]=="0"
                and x["claim_ceiling"]=="S0" for x in rows),
            "STAGE47_FROZEN_SOURCE_CLAIMS_CHANGED")
    require(not summary["exact_MRI_acquisition_scanner_or_segmentation_protocol_equivalence"]
            and not summary["between_cohort_difference_formal_test_performed"]
            and not summary["paired_test_retest_or_intervention_performed"],
            "STAGE47_UNSUPPORTED_CROSS_COHORT_INFERENCE")
    require(abs(float(summary["internal_tcgaliHC_native_pv_rater1_median_abs_change_pct"])-74.8808)<.005,
            "STAGE47_INTERNAL_MRI_SOURCE_RESULT_DRIFT")
    require(abs(float(summary["external_openswiss_native_pv_rater1_median_abs_change_pct"])-64.635863)<.002,
            "STAGE47_EXTERNAL_MRI_SOURCE_RESULT_DRIFT")
    require(int(summary["source_ICC14_rater_pairs_exist"])==14 and
            int(summary["external_second_reader_index_lesion_pairs_exist"])==3,
            "STAGE47_READER_COUNT_FALSELY_PROMOTED")
    require(summary["clinical_eligible_n"]=="NOT_ASSESSED" and
            summary["MRI_RNA_biological_tests"]==0 and
            summary["clinical_biological_claim_ceiling"]=="S0",
            "CLINICAL_RNA_CLAIMS_PROMOTED")
    risk=Counter(x["novelty_risk"] for x in LITERATURE)
    require(risk["HIGH"]>=4 and len({x["doi"].lower() for x in LITERATURE})==6,
            "DIRECT_PRIOR_ART_NOVELTY_UNIVERSE_UNSOUND")
    require(sum(x["decision"]=="PROHIBITED" for x in CLAIMS)>=7,
            "RESTRICTED_CLAIM_GUARD_NOT_COMPREHENSIVE")
    return dict(stage=ID,date=datetime.date.today().isoformat(),
      verified_original_patient_evidence_n=73,
      cohort_native_mri_internal_n=14,cohort_external_mri_n=59,
      direct_prior_art_comparator_papers=6,
      prior_art_high_overlap_n=risk["HIGH"],
      invalid_or_prohibited_proposed_claims=sum(x["decision"]=="PROHIBITED" for x in CLAIMS),
      explicit_preregistration_status="POST_RESULTS_ANALYSIS_PLAN_LOCK_NOT_PROSPECTIVE_PREREGISTRATION",
      novelty_statement="CONDITIONAL_NARROW_HCC_VENOUS_PIXEL_GRID_MAGNITUDE_VS_RANK",
      generic_mri_radiomics_reproducibility_novelty="NO",
      voxel_resampling_first_ever_novelty="NO",
      independent_test_retest_available_n=0,
      independent_current_expert_roi_adjudication_n=0,
      MRI_RNA_qualified_patient_n="NOT_ASSESSED",
      MRI_RNA_biology_tests=0,
      MRI_RNA_biological_claim_ceiling="S0",
      submission_readiness="HOLD_PENDING_FULL_PAPER_PRIOR_ART_EXPERT_REVIEW_AND_EQUAL_ESTM",
      methods_thesis_direction="CONDITIONAL_GO",
      remaining_independent_categories=3,
      next_computational_task="RATER1_ONLY_PATIENT_RANK_SPEARMAN_INTERNAL14_FROM_ORIGINAL_PAIRED_SOURCE_FEATURES",
      next_human_task="INDEPENDENT_ABDOMINAL_EXPERT_REVIEW_OR_RESTRICT_TO_IMAGE_METHODS_QC",
      next_literature_task="FULL_TEXT_CLOSE_HCC_MRI_PREPROCESSING_METHODS_AND_NOVELTY_REVIEW")
def write(out,s,meta):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stage48_direct_prior_art_source_comparison.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(LITERATURE[0]))
        w.writeheader();w.writerows(LITERATURE)
    with (out/"stage48_thesis_claim_permission_and_rejection.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(CLAIMS[0]))
        w.writeheader();w.writerows(CLAIMS)
    (out/"stage48_thesis_novelty_clinical_S0_gate.json").write_text(json.dumps(s,indent=2)+"\n")
    (out/"stage48_live_literature_metadata_check.json").write_text(json.dumps(meta,indent=2)+"\n")
    lines=[
      "# Stage48: direct literature novelty comparison and MSc methods claim ceiling",
      "",
      "**Current decision: methods MSc CONDITIONAL GO; submission readiness HOLD; MRI-RNA biology 0/12, S0.**",
      "",
      "The plan is **post-results locked exploratory analysis** and is NOT a prospective preregistration.",
      "The literature review is a targeted set, **not a systematic search or proof of novelty absence**.",
      "",
      "## Key direct prior works",
      "",
      "| Primary work | Overlap and what is already known | Remaining legitimate distinction |",
      "|---|---|---|"
    ]
    for x in LITERATURE:
        lines.append("| ["+x["short"]+"]("+x["source_url"]+") | "+
                     x["overlap"]+" | "+x["distinction"]+" |")
    lines += [
      "",
      "## Source-cohort scope that genuinely holds",
      "",
      "- n14 native original TCGA PV reader1 absolute GLCM Contrast native→3mm shift median **74.8808%**.",
      "- n59 independent OpenSwiss venous original MRI source shift median **64.635863%**;",
      "  existing n59 paired patient-rank Spearman **0.940795** from Stage46,",
      "  but internal n14 matching rater1-only rank is **NOT_YET_VERIFIED**.",
      "- Internal n14 14×2 reader ICC and external selected index lesion reader2 subset n=3",
      "  are distinct reader-reliability questions, NOT extra patients.",
      "- No statistical evidence currently makes the cohorts scanner or sampling exchangeable.",
      "",
      "## GO/HOLD/STOP",
      "",
      "**GO:** source-backed numerical image preprocessing sensitivity and source-limited reproducibility results.",
      "**HOLD:** novel MSc submission: full-text close prior art, source protocol comparability and independent",
      "abdominal reviewer anatomy/ROI adjudication absent; narrow claims if expert review not possible.",
      "**STOP:** first-ever MRI reliability, genuine scan test-retest, HCC prognosis, HCC treatment response,",
      "MRI-index lesion→GDC RNA molecular mechanisms, or original MRI-before-all-HCC-treatments without evidence.",
      "",
      "## Exact next proof (three independent categories)",
      "",
      "1. Recalculate original n14 reader1 patient-rank Spearman using full native/3mm paired features",
      "   from existing successful original feature artifact. Do not replace with two-reader patient-mean rank.",
      "2. Obtain appropriately qualified blinded source-image/contour anatomy adjudication, OR clearly",
      "   limit work to computational measurements on provided masks with no expert-validated anatomical claim.",
      "3. Full-text review of the high-overlap 2022 HCC precision, 2023 HCC 3mm,",
      "   2024 brain MRI bin-width/resampling papers before asserting distinct contribution.",
      "",
      "## Literature identity crosscheck",
      ""]
    for x in meta:
        lines.append("- "+x["id"]+": "+x["metadata_status"]+
                     ((" ("+str(x["returned_year"])+")") if x["returned_year"] else ""))
    md="\n".join(lines)+"\n"
    (out/"stage48_master_thesis_literature_gap_and_protocol_gate.md").write_text(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(md)
    print("HCC_STAGE48_PRIOR_ART_CLAIM_CEILING_VERIFIED",json.dumps(s,sort_keys=True),flush=True)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage47-csv",type=Path)
    ap.add_argument("--stage47-json",type=Path)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage48_novelty"))
    ap.add_argument("--verify-metadata-online",action="store_true")
    ap.add_argument("--offline-test",action="store_true")
    a=ap.parse_args()
    require(len(LITERATURE)==6 and len(CLAIMS)>=10,"STAGE48_LITERATURE_CLAIM_FIXTURE_CHANGED")
    print("HCC_STAGE48_SOURCE_ONLY_NOVELTY_CLAIM_FIXTURE_PASS")
    if a.offline_test:return
    require(a.stage47_csv and a.stage47_json and
            a.stage47_csv.is_file() and a.stage47_json.is_file(),
            "STAGE47_IMMUTABLE_SOURCE_RESULTS_REQUIRED")
    s=assess(records(a.stage47_csv),json.loads(a.stage47_json.read_text()))
    metadata=citation_metadata_online(LITERATURE) if a.verify_metadata_online else [
       dict(id=x["id"],doi=x["doi"],source_url=x["source_url"],
            metadata_status="CURATED_OFFICIAL_PRIMARY_SOURCE_NOT_LIVE_CROSSREF_AUDITED",
            returned_title="",returned_year=None,error="") for x in LITERATURE]
    s["bibliography_live_crossref_confirmed_n"]=sum(
          x["metadata_status"]=="LIVE_CROSSREF_DOI_TITLE_YEAR_PASS" for x in metadata)
    s["bibliography_crossref_review_or_unavailable_n"]=len(metadata)-s["bibliography_live_crossref_confirmed_n"]
    write(a.out_dir,s,metadata)
if __name__=="__main__":
    main()
