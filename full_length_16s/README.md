# KIST Full-Length 16S (PacBio Revio HiFi)

## Scope and files

- Contract: H209SC26096091; 20K reads per sample Revio full-length 16S.
- Drive project folder: https://drive.google.com/drive/folders/1070GDz6WnKV23Ygzgs08idwO1p4-xYm5
- Existing metadata workbook has 110 rows, including PC twice and NC twice.
- Vendor result archive is about 2.17 GB; it is NOT yet verified to contain raw FASTQ.
- The unique sample identifier joins the sample name with the Novogene FKDN identifier; this is necessary for duplicated PC and NC labels.

## Four requested scenarios

Scenario | Keep PC/NC? | Keep three explicitly excluded samples?
--- | --- | ---
all | Yes | Yes
no_controls | No | Yes
no_three | Yes | No
no_controls_no_three | No | No

The exact three excluded sample names are configurable in the notebook EXCLUDE_THREE_SAMPLE_IDS. They MUST match a single full sample ID, or a unique sample name, in the validated workbook. If no names have been provided the third and fourth analyses are visibly BLOCKED, never guessed or silently declared PASS.

For each scenario we create:
- Subset-specific ASV count table and sample metadata.
- List of all explicitly excluded sample IDs and exclusion reason.
- Alpha diversity: observed ASVs and Shannon.
- Beta diversity: Bray-Curtis matrix and PCoA scatter.
- Genus abundance bar chart if taxonomy is present.
- HTML report and per-variant CSV outputs.
- Overall status and comparison CSV / JSON.

These four scenarios are computed from a common ASV table, with alpha/beta diversity recomputed independently. They are NOT equivalent to independently repeating DADA2 inference four times. If FASTQ is available, the tool can additionally export sample-filtered manifests to support separate denoising sensitivity analyses.

## Files

- notebooks/KIST_FullLength16S_Colab.ipynb: authenticated Drive notebook
- src/full16s.py: sample mapping, file inventory, FASTQ manifest, diversity report.
- src/subset_analyses.py: four sample filtering analyses with validation.
- scripts/run_qiime2.sh: QIIME 2 DADA2 denoise-ccs from HiFi single-end FASTQ.
- tests/test_scenarios.py: synthetic scenario tests.
- .github/workflows/full-length-16s-ci.yml: GitHub Actions validation.

## Workflow

1. Open Colab from Drive/notebooks and allow Drive access.
2. Run setup and sample mapping (expected 110 rows; four PC/NC controls).
3. Enter exactly three excluded sample IDs in EXCLUDE_THREE_SAMPLE_IDS.
4. For the vendor archive, set DOWNLOAD_VENDOR_ZIP=True to inspect its contents.
5. For raw analysis upload HiFi FASTQs to Drive/raw_fastq, set DOWNLOAD_RAW_FASTQ and configure true primer sequences and a compatible SILVA reference classifier.
6. Run QIIME 2 2026.10 where resources permit, or use a compatible existing feature table. Generate the four reports and upload to analysis_outputs.

No raw FASTQs or vendor result ZIP are checked into GitHub. GitHub stores code and synthetic test fixtures only. Drive holds source data and reports.

Scientific references:
- QIIME 2 2026.10 official installation: https://library.qiime2.org/quickstart/qiime2
- DADA2 PacBio CCS denoising: https://amplicon-docs.qiime2.org/en/stable/references/plugins/dada2/
