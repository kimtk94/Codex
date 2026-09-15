# Digital Health × Omics — Top 3 Master's Thesis Proposals (2026-09)

## Executive decision

**Primary dataset: NIH All of Us CDR v9 Controlled Tier.**

Why this changed from the initial UK Biobank-first plan:

- Sungkyunkwan University Research & Business Foundation is listed as an All of Us institution with **Registered + Controlled Tier** access.
- All of Us CDR v9 (released 2026-06-26) now combines:
  - >535,000 short-read WGS participants
  - >481,000 participants with EHR
  - >68,000 participants with Fitbit data
  - 9,969 proteomics samples with expression counts for >5,000 proteins
  - 8,980 RNA-seq samples
- All of Us gives each registered researcher initial cloud credits and supports JupyterLab, R, Hail/PLINK and Git integration.
- UK Biobank remains excellent for external validation, but new UKB applications are temporarily paused and planned to reopen in late 2026.

The first analysis in All of Us should therefore be a **Stage 0 modality-overlap feasibility check** before final topic lock.

---

# Ranked recommendation

| Rank | Proposal | Novelty | Feasibility | Digital-health identity | Omics depth | Thesis fit |
|---|---|---:|---:|---:|---:|---:|
| 1 | Longitudinal Fitbit sleep/circadian phenotype × proteomics × pQTL/causal triangulation | 5/5 | 3.5/5* | 5/5 | 5/5 | **4.6/5** |
| 2 | Longitudinal Fitbit sleep/activity phenotype × PRS/APOE × incident ADRD | 4/5 | 4.5/5 | 5/5 | 4/5 | **4.5/5** |
| 3 | Pre-diagnostic EHR trajectory × WGS/PRS/rare variants × ADRD/PD | 3.5/5 | 5/5 | 3.5/5 | 4.5/5 | **4.2/5** |

\* Proposal 1 feasibility depends on the participant overlap between Fitbit and CDRv9 proteomics. That count must be measured in the Workbench before committing.

---

# Proposal 1 — Recommended if the overlap is sufficient

## Working title

**Longitudinal Digital Sleep and Circadian Phenotypes Associated with the Plasma Proteome and Neurodegenerative Risk**

Alternative thesis title:

**Integrating Longitudinal Wearable Phenotypes, Plasma Proteomics, and Human Genetics to Identify Molecular Pathways Linking Sleep/Circadian Health to Neurodegeneration**

## Core question

Which plasma proteins are reproducibly associated with longitudinal wearable-derived sleep/circadian phenotypes, and do genetic instruments for those proteins support a causal role in Alzheimer's disease or related neurodegeneration?

## Why this is preferable to generic physical-activity proteomics

Physical activity × proteomics is already becoming crowded. Recent UK Biobank studies have derived proteomic signatures of MVPA and proteomic aging.

The less saturated direction is:

- longitudinal sleep regularity
- sleep timing / chronotype-like digital features
- day-to-day variability
- resting heart-rate rhythm
- circadian rest–activity regularity

combined with a newly released proteomic layer.

All of Us is particularly attractive because its Fitbit data can span months to years, unlike the one-week UK Biobank wrist-accelerometer protocol.

## Stage 0 gating rule

Count participants satisfying:

1. valid Fitbit data
2. proteomics available
3. WGS or genotyping available
4. sufficient EHR follow-up

Decision rule:

- **N >= 1,500:** proceed with full wearable + proteomics + genetics proposal.
- **500 <= N < 1,500:** use a reduced, pre-specified protein panel / dimension reduction and external pQTL instruments.
- **N < 500:** pivot primary thesis to Proposal 2; keep proteomics as a secondary exploratory aim.

These thresholds are pragmatic design gates, not formal power-analysis results.

## Digital phenotype features

### Sleep

Primary:
- sleep duration
- sleep midpoint
- sleep onset and wake-time variability
- sleep regularity index
- weekend-weekday shift / social jetlag proxy
- wake after sleep onset / fragmentation
- REM/deep/light fraction where device generation supports stages

Longitudinal:
- 30-day mean
- 30-day SD / coefficient of variation
- 90-day stability
- intra-individual entropy
- missingness/adherence metrics

### Activity / cardiovascular digital phenotype

Secondary:
- daily steps
- active minutes
- activity fragmentation
- resting / daily heart rate
- heart-rate-per-step type measures
- circadian amplitude and acrophase

## Proteomics

CDRv9 currently provides 9,969 proteomic samples and >5,000 protein expression features.

Primary analysis:

1. protein-level QC
2. normalization / batch covariates as documented by All of Us
3. linear models:
   protein ~ digital phenotype + age + sex + BMI + ancestry PCs + smoking + comorbidity + device/adherence covariates
4. Benjamini-Hochberg FDR
5. pathway enrichment
6. WGCNA or sparse latent factors only as a secondary analysis

## Genetics / causal layer

Use two complementary routes:

### Route A — External pQTL instruments

Use established pQTL resources such as UKB-PPP / other large pQTL studies for instruments.

For proteins associated with the digital phenotype:

- cis-pQTL selection
- LD clumping
- protein -> ADRD/AD/PD two-sample MR
- Steiger directionality
- heterogeneity / pleiotropy sensitivity where instrument count allows
- coloc between protein pQTL and disease GWAS locus

### Route B — All of Us internal genetics

If the proteomics/WGS overlap supports it:

- cis-pQTL association inside the All of Us multi-omics subset
- ancestry-aware replication
- compare effect direction to external pQTL resources

Do **not** interpret a protein pQTL MR as proof that wearable behavior causally changes the protein. The causal claim is protein -> disease; the wearable-protein association supplies biological context and triangulation.

## Primary outcome

Recommended:
- incident ADRD

Secondary:
- Parkinson's disease
- all-cause dementia
- biological-aging phenotype derived from available clinical labs, if sample coverage is adequate

## Main models

1. Digital phenotype -> protein
2. Digital phenotype -> incident ADRD
3. Protein -> ADRD using MR/coloc
4. Digital phenotype + protein score -> ADRD prediction
5. Optional interaction: digital phenotype × APOE/PRS

## Expected figures

**Figure 1. Cohort and multimodal data flow**
- participant counts and overlap
- Fitbit/proteomics/WGS/EHR timeline

**Figure 2. Digital phenotype landscape**
- sleep/activity distributions
- correlation heatmap
- longitudinal reliability

**Figure 3. Wearable–proteome association**
- Manhattan-style protein plot
- volcano plot
- top proteins and pathways

**Figure 4. Causal triangulation**
- pQTL MR forest plot
- coloc regional plots for top proteins

**Figure 5. Clinical relevance**
- incident ADRD curves / risk model
- clinical-only vs digital vs digital+proteomic model performance

## Major risks

- Fitbit–proteomics overlap may be small.
- Fitbit device generation and BYOD/WEAR source can create measurement heterogeneity.
- Temporal ordering between proteomics collection and wearable exposure must be explicitly handled.
- Proteomics selection may not be population-random.

## Publishable minimal version

If overlap is moderate:

**Longitudinal sleep regularity and plasma proteomic signatures in All of Us**

Then use external pQTL/MR as a validation/candidate-prioritization layer rather than building internal pQTLs.

---

# Proposal 2 — Best fallback / strongest practical thesis

## Working title

**Interaction of Longitudinal Wearable-Derived Circadian Phenotypes and Genetic Risk on Incident Alzheimer's Disease and Related Dementias**

## Core question

Does longitudinal sleep/circadian regularity measured by Fitbit modify or add to genetic risk for incident ADRD?

## Why the generic version is no longer novel enough

A 2026 All of Us study already evaluated modifiable risk factors together with APOE/PRS for incident ADRD.

Therefore the thesis should **not** be:

> lifestyle + PRS -> ADRD

Instead it should focus on digital time-series phenotypes that are not well represented by conventional risk-factor summaries.

Recommended differentiators:

- sleep regularity / variability rather than average sleep duration
- circadian amplitude and timing
- multi-year trajectory
- within-person change
- interaction with PRS/APOE
- mediation/triangulation rather than simple additive prediction

## Cohort

CDRv9:

- age >= 50
- no ADRD at index
- sufficient EHR history
- sufficient Fitbit observation
- WGS/genotyping passing QC

A prior All of Us wearables resource reported that a substantial subset of Fitbit participants also contributed EHR, physical measurements, genomics and surveys, so the multimodal overlap is already proven to be workable.

## Genetic features

Primary:
- APOE genotype
- established ADRD PRS

Secondary:
- pathway-specific PRS
- rare damaging variant burden in selected dementia genes if sample size supports it

## Digital features

Primary:
- sleep regularity index
- sleep midpoint variability
- sleep duration variability
- rest-activity rhythm amplitude
- resting HR variability

Secondary:
- steps / activity regularity
- heart-rate-per-step type phenotype

## Statistical analysis

1. Cox model for incident ADRD
2. baseline:
   clinical covariates only
3. + PRS/APOE
4. + digital phenotype
5. + PRS × digital interaction
6. discrimination/calibration:
   - C-index
   - time-dependent AUC
   - calibration
7. sensitivity:
   - ancestry-aware analyses
   - minimum wearable observation thresholds
   - lag periods to reduce reverse causation

## Expected figures

1. cohort flow + timelines
2. digital phenotype trajectories
3. PRS × digital phenotype interaction plot
4. cumulative incidence / survival curves
5. incremental model-performance figure

## Main risk

A broad lifestyle/genetic-risk question is now partially occupied in the literature. Novelty depends on using **high-resolution longitudinal digital phenotyping**, not conventional lifestyle categories.

---

# Proposal 3 — Highest statistical feasibility, lower digital-health distinctiveness

## Working title

**Pre-diagnostic EHR Trajectories and Genomic Risk for Early Identification of Alzheimer's and Parkinson's Disease**

## Core question

Can temporal EHR trajectories combined with PRS/rare-variant burden identify future ADRD or Parkinson's disease earlier than either clinical or genomic information alone?

## Dataset strength

All of Us CDRv9 has:

- >481,000 participants with EHR
- >535,000 with short-read WGS
- >99,000 participants with newly released clinical-note-derived NLP concept codes from selected sites

This makes it the strongest option if a large sample and reliable thesis completion are prioritized.

## Phenotypes

Outcome:
- incident ADRD
- optional PD parallel endpoint

EHR predictors:
- diagnoses
- medications
- lab trends
- healthcare utilization
- cardiovascular/metabolic comorbidity
- depression/sleep disorders
- sensory impairment
- NLP-derived concept codes as an optional V2

Genetic predictors:
- APOE
- ADRD PRS
- PD PRS
- selected rare-variant burden

## Analysis

1. define prediction landmark, e.g. 3 or 5 years before diagnosis
2. construct 1-, 2-, 3-year temporal EHR windows
3. baseline Cox/logistic model
4. gradient boosting or regularized regression
5. add genomic features
6. temporal holdout
7. subgroup performance by ancestry
8. SHAP / interpretable feature ranking

## Expected figures

1. timeline/landmark design
2. top longitudinal EHR trajectory features
3. PRS distribution and risk gradient
4. model comparison
5. calibration and subgroup generalization

## Main risk

This is a strong biomedical informatics thesis, but it is less clearly "Digital Health × Omics" than a wearable-based project.

---

# Direct comparison for thesis selection

## If the goal is originality

Choose **Proposal 1**.

CDRv9 proteomics is new, and wearable × newly released proteomics × genetics is still sparsely occupied.

## If the goal is probability of finishing the master's thesis

Choose **Proposal 2**.

The data modalities already have demonstrated multimodal overlap, analysis is manageable, and the clinical story is clear.

## If the goal is sample size / machine-learning strength

Choose **Proposal 3**.

It has the largest usable cohort and fewest modality-overlap constraints.

---

# Final recommendation

## Preferred thesis

**Longitudinal wearable-derived sleep/circadian phenotypes × plasma proteomics × pQTL causal prioritization of neurodegenerative pathways**

with a pre-specified fallback:

> If Fitbit–proteomics overlap is insufficient, pivot to wearable × genomics × incident ADRD using the exact same digital phenotype pipeline.

This approach preserves the Digital Health identity while ensuring the project is not blocked by an unexpectedly small proteomics overlap.

---

# Immediate next actions

1. Register / confirm individual All of Us Controlled Tier access under SKKU R&BF.
2. Create a CDRv9 Controlled Tier workspace.
3. Run Stage 0 overlap counts:
   - Fitbit
   - EHR
   - WGS
   - proteomics
   - intersections
4. Measure temporal overlap:
   - proteomics collection date vs valid wearable window
   - EHR follow-up after wearable/proteomic index
5. Freeze Proposal 1 vs Proposal 2 based on the overlap count.
6. Build the first analysis dataset without pulling participant-level data outside the Workbench.
7. Pre-register primary digital features and primary endpoint before proteome-wide association.

---

# Evidence notes

Key 2026 feasibility observations used in this proposal:

- All of Us CDRv9 was released in June 2026 and includes >747,000 participants overall.
- CDRv9 includes >68,000 Fitbit participants, >535,000 WGS participants, >481,000 EHR participants, 9,969 proteomics samples, and 8,980 RNA-seq samples.
- Proteomics contains expression measures for >5,000 proteins.
- Sungkyunkwan University Research & Business Foundation is listed for Registered and Controlled Tier access.
- All of Us supports international researchers when their institution has a DURA.
- Fitbit tables include activity, heart-rate and sleep data, including newly expanded CDRv9 sleep summary tables.
- All of Us provides $300 initial cloud credits to registered researchers.
- UK Biobank new access applications are temporarily paused with planned reopening in late 2026.
