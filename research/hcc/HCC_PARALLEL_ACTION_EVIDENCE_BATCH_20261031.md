# HCC MRI × RNA — GitHub Actions parallel evidence batch, 2026-10-31

## Verified execution

- [GitHub Actions HCC Public Cohort Audit #147](https://github.com/kimtk94/Codex/actions/runs/41156497628): **all three independent gate jobs PASS**, downstream joint readiness **PASS**, and legacy offline regression suite **PASS**.
- Code commit that introduced parallel jobs: `dcca58ed993a01bd8edc1f899681191ae9b7ae38` on PR branch `feat/hcc-public-ci-20261022` ([PR #228](https://github.com/kimtk94/Codex/pull/228)). The latest documentation commits do not change patient decisions.
- Workflow: [`.github/workflows/hcc-public-cohort-audit.yml`](../../.github/workflows/hcc-public-cohort-audit.yml); deterministic integrator [`ci/mri_parallel_batch_gate.py`](ci/mri_parallel_batch_gate.py).
- Source-data policy: the four batch gates use **existing frozen source QC files**, not new large MRI, DICOM, or GDC raw expression downloads. A green run is **cross-source consistency evidence**, not new clinical patient eligibility proof.
- Artifact `hcc-batch-joint-readiness`: per-patient `hcc_mri14_joint_clinical_purity_image_rna_gate.csv` plus `hcc_batch_multi_job_readiness_summary.json`, 30-day artifact retention. 3 separate input artifacts `hcc-batch-clinical`, `hcc-batch-purity`, `hcc-batch-source` are independently inspectable.

## Workflow graph (all tests fail closed)

| Stage | Independent GitHub job | Actual checked evidence | Result run #147 |
|---|---|---|---|
| 1/4 | `hcc-batch-clinical` | 14 GDC source-derived candidate patients, 10 originally dated affirmative intervention rows, HCC diagnosis context vs cecum/appendix surgery, P0=4/P1=5/P2=5 and **all HOLD** | **PASS** |
| 2/4 | `hcc-batch-purity` | Independent PanCanAtlas ABSOLUTE DNA vs Aran CPE sources at **exact 16-char specimen level**, values/ranges/missingness, barcodes and no clinical promotion | **PASS** |
| 3/4 | `hcc-batch-source-identity` | Frozen 14 ROI index lesions including A10Y tumor3, exact 14 matched GDC RNA UUID/primary specimen, actual source checksum QC, Hallmark 2025.1 score provenance, original 8 ICC-stable features and 3×4=**12** locked hypothesis family | **PASS** |
| 4/4 | `hcc-batch-readiness` | Downloads artifacts from **all 3 preceding jobs**, checks patient sets, specimen barcodes, risk flags and eligibility claims, creates joint case-level CSV/summary, displays GO/HOLD/STOP in GitHub run summary | **PASS** |
| In parallel | `offline-tests` | Existing 27-checkpoint evidence linter and all other HCC fixture tests, new integrator fail-closed regression | **PASS** |

Jobs 1, 2 and 3 run independently and concurrently; job 4 has `needs` dependencies so a failed/missing source report cannot silently yield an apparently valid integrated result. New batch outputs are read-only: they do not change TCGA patient eligibility records or execute MRI–RNA statistics.

## Joint results

- **14** frozen technical candidate patients; source barcode, MRI PV representative index lesion, GDC primary tumor RNA file identity and patient-level gene-set score records cross-check **14/14**.
- Clinical treatment/anatomy review priority = **P0 four** (affirmative prior treatment within HCC diagnosis context), **P1 five** (other-site dated surgery or conflicting diagnoses), **P2 five** (prior-treatment No-only records but pretreatment MRI not independently proven).
- PanCanAtlas DNA ABSOLUTE specimen purity proxy = **13/14**, historical Aran CPE = **14/14**. Two cases have `|ABSOLUTE − CPE| > 0.20`: **TCGA-G3-A3CJ** and **TCGA-G3-A7M7**. This is *cross-method/provenance discordance*, not proof that either reference is erroneous.
- Joint high-priority **clinical P0 + purity P0** is **TCGA-DD-A4NH**. Its low DNA/CPE values and HCC-context treatment record both require independent adjudication; coincidence of flags does not demonstrate causality.
- **ALL 14 unresolved**, not 14 excluded. Eligible patient count **NOT ASSESSED**; excluded count **NOT ASSESSED**; original image pretreatment status and same-lesion MRI↔RNA tissue identity **NOT VERIFIED**.
- Frozen 3 PV MRI reader-stable features × 4 Hallmark score hypotheses = **12 predefined tests**, **none executed**. Paper inferential threshold was set at a minimum of **10 eligible participants** and cannot be satisfied by automatically counting the 14 technical candidates.
- Counterfactual denominator only: if all 4 HCC-context P0 were independently excluded, maximum possible eligible n would be 10; any further exclusion makes n ≤ 9, violating the locked exploratory inferential plan. **These are hypothetical scenarios, not actual patient exclusions.**
- Final decision = technical evidence integrity **GO**; clinical case eligibility **HOLD**; planned 12 MRI–RNA association tests **STOP until verified**. Manuscript significance claim ceiling **S0**. HCC-14/16 PARTIAL, HCC-17/20 PENDING.

## What counts as real clinical progress (not automatable by this run)

1. Qualified radiology reviewer checks selected PV tumor source mask/lesion and verifies tumor anatomy, especially A10Y tumor3.
2. A source-authoritative, deidentification-aware bridge establishes patient MRI-before-intervention and MRI-to-resected primary tumor tissue relation. GDC diagnosis-relative treatment dates must **not** be directly subtracted from shifted TCIA DICOM dates.
3. Clinically responsible reviewer resolves four HCC-context treatment cases, unrelated cecal/appendiceal surgery in A5W4, and unexplained missing treatment days in the other cases.
4. RNA material purity is assessed at a defensible analyte/portion level; historical DNA ABSOLUTE/CPE sample proxies alone cannot confirm the exact sequenced STAR-count RNA aliquot or purity correction.
5. Final patient flow must be explicitly signed off (eligible + excluded + unresolved = 14); main 12 tests remain blocked until all study gates pass.

## Automation behavior

- Trigger: HCC PR edits and configured GitHub Actions `workflow_dispatch`; the existing repository-level weekly schedule applies **only to the default branch**. PR branch execution is verified by run #147, but the unmerged branch is **not** claimed to have a deployed production weekly schedule.
- Artifact naming and patient-level identity checks are stable per workflow run; final summary is displayed in the GitHub run's Step Summary. Data outputs are held for 30 days by GitHub Actions, so retain this method/result in the repository. No server shell `set -e`, no Colab work, and no alteration to the pre-RNA frozen 12 hypotheses.
- If one parallel job fails, the downstream readiness job is skipped and does **not** label the cohort eligible; read the failed job's own log and artifact to identify the blocker.
