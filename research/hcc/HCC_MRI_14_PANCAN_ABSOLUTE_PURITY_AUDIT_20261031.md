# HCC MRI 14 — PanCanAtlas ABSOLUTE DNA purity × primary tumor RNA specimen crosswalk

Date: 2026-10-31 KST. **Technical provenance GO; clinical eligibility remains HOLD.**

## Real source acquisition and QA

- Source: [NCI GDC TCGA PanCanAtlas ABSOLUTE purity/ploidy](https://gdc.cancer.gov/about-data/publications/pancanatlas), official file `TCGA_mastercalls.abs_tables_JSedit.fixed.txt`, source UUID `4f277128-f793-4354-a13d-30cc7fe9f6b5`.
- Exact API source https://api.gdc.cancer.gov/data/4f277128-f793-4354-a13d-30cc7fe9f6b5
- Real [GitHub Actions run #121](https://github.com/kimtk94/Codex/actions/runs/41090891246), original source downloaded **901,812 bytes**, SHA-256 `f430a975433d82e0098d7405619d4f12a0c765fcd97e7d63cc9b1de7f2d763cd`. Header `array, sample, call status, purity, ploidy, Genome doublings, Coverage for 80% power, Cancer DNA fraction, Subclonal genome fraction, solution`.
- [Permanent 14-patient sample barcode/purity/ploidy crosswalk](HCC_MRI_14_PANCAN_ABSOLUTE_PURITY_PROXY_20261031.csv); the full run artifact includes source rows and reviewer statuses.
- This dataset uses DNA copy-number/cellularity estimates, **not** RNA purity. Do not call a match to the same 16-character TCGA specimen identifier the **same DNA and RNA aliquot**. DNA source barcodes typically contain D, whereas GDC expression sources have R analyte codes.
- [Aran, Sirota & Butte, Nat Commun 2015](https://doi.org/10.1038/ncomms9971) discusses why ABSOLUTE, ESTIMATE, LUMP, and pathology IHC purity measures can disagree. An RNA-specific or consensus CPE estimate is a separate method and must be independently verified.

## Verified findings — technical RNA specimen matched at 16-character level

- **13/14** MRI–RNA candidates had an official ABSOLUTE DNA-derived purity estimate with exactly matching 16-character TCGA tumor specimen barcode (`TCGA-XX-XXXX-01A`) as the RNA sample. **0/14** were explicitly verified as the *same analyte/aliquot*.
- **1/14 has no matching ABSOLUTE patient** in this official source: `TCGA-DD-A4NJ`. This means *missing*, not zero purity.
- Among the 13 matched proxy estimates: median **0.74**, min **0.20**, max **1.00**.
- **Three patients** have DNA-derived purity below 0.50. This is a *review threshold used here to identify confounding*, **not a predefined statistical exclusion criterion** and not directly linked to the same RNA analyte.

| Patient | ABSOLUTE DNA purity proxy | QC priority | Why |
|---|---:|---|---|
| TCGA-G3-A3CJ | 0.20 | P0 | Very low DNA-derived purity; linked pathology slide tumor-cells minimum was 100%, showing method/tissue discordance |
| TCGA-DD-A4NH | 0.34 | P0 | Low purity, linked pathology slide 75%; separately flagged clinical pre-tissue Yes treatment day |
| TCGA-G3-AAV3 | 0.47 | P1 | Low/moderate DNA-derived purity, linked slide 75% |
| TCGA-DD-A4NJ | Missing | P1 | No ABSOLUTE record, previously linked slide tumor cells 50%, nuclei 100%; seek independent CPE/ESTIMATE |
| All other 10 matched cases | 0.58–1.00 | Review as normal | Still DNA copy-number proxy only; no exact RNA-aliquot tumor purity certification |

## Why this matters for the frozen four Hallmark pathways

- The observed strong RNA-only pathway correlation (Angiogenesis vs EMT rho **0.982**) could be influenced by non-tumor stromal composition, site and tissue purity; this is **a confounding hypothesis requiring validation**, not an observed proof of mediation.
- DO NOT use pathology `percent_tumor_cells`, `percent_tumor_nuclei`, GDC `tumor_descriptor`, ABSOLUTE, and RNA-specific `ESTIMATE` interchangeably: each measures a different specimen slice or algorithmic quantity.
- In any downstream eligible subset, predeclare sensitivity results **with and without** the three below-0.50 specimen-level DNA proxies and report missingness; with n=14 or fewer, fitting multivariable models to four collinear Hallmarks risks unstable effect estimates.
- If using ABSOLUTE as a covariate later, require sample ID and temporal eligibility sign-off, full disclosure of one missing value and the resulting smaller n. Do not silently impute missing purity or exclude low-purity cases as a way to improve associations.

## New gate status, still NOT eligible

- **HCC-16 = PARTIAL**: four Hallmark scores are technically validated and now DNA-derived *same-specimen* purity data available for 13/14, but **matched RNA aliquot purity, clinical chronology, batch effects and other methods remain unverified**.
- **HCC-14 = PARTIAL**: earlier GDC clinical source audit flagged 5 potential Yes treatment dates on/before tissue collection, no safe MRI date join; ABSOLUTE does not address the timing problem.
- **HCC-17 = PENDING**: clinical/radiologist eligibility n still NOT ASSESSED.
- **HCC-20 = PENDING**, primary 12-image/RNA tests not run; claim ceiling **S0**.

## Next check

- Source-match independent CPE/ESTIMATE/LUMP values from [Aran et al. Supplementary Data 1](https://doi.org/10.1038/ncomms9971) at the **same 16-character specimen** where available; do not treat estimates computed from older RNA-seqV2 RSEM as the exact GDC STAR aliquot.
- Reconcile patients `TCGA-G3-A3CJ`, `TCGA-DD-A4NH`, `TCGA-G3-AAV3`, and missing `TCGA-DD-A4NJ` against both published purity and linked slides.
- Obtain source clinical date/pretreatment MRI verification before biological testing; a specimen purity estimate cannot unblock a pretherapy MRI chronology gate.
- Repro script: `research/hcc/ci/mri_pancan_absolute_purity_audit.py`; no raw ABSOLUTE pan-cancer table committed, only 14-case derived provenance.
