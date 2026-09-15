# All of Us CDRv9 Stage 0 Feasibility Check

Goal: determine whether Proposal 1 (Fitbit × proteomics × genetics) has enough multimodal overlap before committing the thesis.

## 1. Workspace

Use:
- All of Us **Controlled Tier**
- CDR v9 / C2025Q4R6
- JupyterLab or R

In Workbench 2.0, set up the environment variables using the official "Getting Started with Verily Workbench" featured workspace before running direct BigQuery code.

## 2. Fitbit participant IDs

Current Fitbit tables include:

- `heart_rate_summary`
- `heart_rate_minute_level`
- `activity_summary`
- `steps_intraday`
- `sleep_daily_summary`
- `sleep_level`
- `sleep_daily_summary_30dayavg`
- `sleep_daily_summary_counts`
- `sleep_daily_summary_ext`
- `sleep_level_short`
- `device`

A robust definition for "has Fitbit" should use the union of participant IDs from the analytical tables rather than the device table alone.

## 3. EHR participant IDs

Use the union / presence of core OMOP domains such as:
- condition_occurrence
- measurement
- drug_exposure
- procedure_occurrence
- visit_occurrence

For a thesis analysis, require a minimum observation history and follow-up duration rather than merely one EHR record.

## 4. Genomics participant IDs

Genomic and multi-omic assets are Controlled Tier resources.

Use the official v9 genomics/multi-omics manifests / auxiliary files to identify:
- srWGS-pass participants
- array-pass participants
- ancestry / PCs / relatedness files

Use the 2026-08-14 v9 genomic update and exclude the small set of samples flagged in current known issues.

## 5. Proteomics participant IDs

CDRv9 contains 9,969 proteomics samples with >5,000 protein expression features.

Use the official proteomics manifest / data dictionary resource to extract only participant IDs at Stage 0. Do not load the entire proteomic matrix simply to calculate overlap.

## 6. Required counts

Create a simple count table:

| cohort | n |
|---|---:|
| Fitbit | |
| Proteomics | |
| WGS | |
| EHR | |
| Fitbit ∩ Proteomics | |
| Fitbit ∩ WGS | |
| Fitbit ∩ Proteomics ∩ WGS | |
| Fitbit ∩ Proteomics ∩ WGS ∩ EHR | |
| Above + age >= 50 | |
| Above + >=12 months usable EHR follow-up | |
| Above + wearable QC | |

## 7. Wearable QC

Recommended initial eligibility:

- at least 21 valid days for basic longitudinal phenotyping
- preferably >=30 valid days
- valid day:
  - >=10 hours wear-time equivalent where derivable
  - and >=100 steps/day for activity analyses
- heart-rate analyses:
  - compute daily adherence from minute-level HR coverage
- run sensitivity analyses at stricter thresholds such as 60/90 valid days

Do not use the same QC rule blindly for sleep, activity and HR phenotypes.

## 8. Temporal alignment

For Proposal 1, explicitly determine:

- date/time span of Fitbit observation
- proteomic biospecimen date
- time gap between wearable window and protein measurement
- EHR outcome follow-up after index

Preferred primary design:

- summarize wearable phenotype in a pre-specified window closest to, and preferably preceding, proteomic sampling
- perform sensitivity analysis restricting the wearable–proteomic interval

Avoid treating multi-year Fitbit measurements collected long after the blood draw as a baseline exposure without temporal qualification.

## 9. Go / pivot rule

### GO — full Proposal 1
If final analyzable overlap is >=1,500.

### CONDITIONAL
If 500–1,499:
- reduce dimensionality
- pre-specify protein modules/panels
- avoid underpowered de novo pQTL discovery
- use external pQTL instruments for MR

### PIVOT
If <500:
- make Proposal 2 (Fitbit × PRS/APOE × ADRD) the primary thesis
- retain proteomics only as exploratory / future work

## 10. First output

The first result should be a non-identifying summary table plus a modality-overlap UpSet plot.

No participant-level data should leave the All of Us Workbench.
