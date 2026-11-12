# KIST PacBio HiFi full-length 16S (P92 / P18)

## Final analysis protocol — PC and NC excluded from every analysis

The provided Nov 12 KIST workbook was rechecked: **110 rows**, **all 110 report names**, and **106 biological group labels** (four control rows have blank group). The older Google Drive workbook appears to lack these filled report labels, so `full16s.samples` applies the validated KIST mapping when blank. These 110 rows represent **two distinct projects**, by their original Excel order:

| Project | Original Excel rows | Original samples | Excluded controls | Analysis preset | Final sample count |
| --- | --- | ---: | --- | --- | ---: |
| P92 | 1–92 | 92 | PC FKDN260619103-1A; NC FKDN260619104-1A | no_controls | **90** |
| P92 | 1–92 | 92 | same PC/NC plus three samples below | no_controls_no_three | **87** |
| P18 | 93–110 | 18 | PC FKDN260618728-1A; NC FKDN260618729-1A | no_controls | **16** |

**Never pool P92 and P18 into one ASV inference or diversity comparison. Never include any PC/NC read in the DADA2 FASTQ manifest or the final ASV matrix.** The 110-sample Excel is used only for validating original ordering and correct per-project sample IDs.

P92 three-sample exclusion, all verified from the original Excel:

- K905_W1_10 — FKDN260619042-1A
- KCT_W3_10 — FKDN260619082-1A
- K902_W3_02 — FKDN260619084-1A

These three are **not** part of P18. P18 therefore has only the 16-sample variant.

## Canonical Colab notebooks

1. [P92 90 samples](https://colab.research.google.com/drive/1Tr3vVKXVIqLr8KrO8hOyAPQs2H7fdGi9)
2. [P92 87 samples](https://colab.research.google.com/drive/14wp4oQNly1KI846Q5arWI1xqUvcdN7UC)
3. [P18 16 samples](https://colab.research.google.com/drive/14fZQxvgMEuy1e6IN5ITeBS3yNcKj71_5)

Canonical Drive notebooks folder:
https://drive.google.com/drive/folders/1DcXmr6w-Jgb2tmcVsBqaOzB2y05zzb8Q

Analysis results:
- P92: https://drive.google.com/drive/folders/1ftL6PEvdc7QAUmW6oAr762cfRglCFp4i
- P18: https://drive.google.com/drive/folders/1hk_I7nHxIDOO_yoDMQ515d3qxcdXynn1

## Execution and safeguards

- The user confirmed that **FASTQ is the only sequencing input**. No precomputed ASV table is assumed. The original ZIP (~2.17 GB) is used only if it actually contains FASTQ; otherwise sample FASTQs must be placed in Drive/raw_fastq. The notebook never requires the user to decompress/re-upload the ZIP. A fresh DADA2 inference requires verified 5' amplification primer sequence. A compatible SILVA classifier QZA is needed for optional taxonomy.
- Each notebook retrieves processing code from this GitHub branch and validates the exact 92/18 workbook split, then creates a strictly PC/NC-free analysis metadata table. The Google Drive API uses **pageSize/pageToken** (not page_size/page_token), correcting the reported TypeError.
- When FASTQ is available, only included samples are downloaded or extracted from ZIP and passed into the **independent, per-notebook DADA2-CCS manifest**. All 90/87/16 FASTQ inputs must be present or the notebook fails; synthetic CI tests cover ZIP scanning, extraction and missing sample rejection.
- This workflow now defaults to FASTQ-only ASV inference. If someone later supplies a previously computed ASV table, `project_splits.py` can still subset and report it, but that is a separate optional reanalysis mode.
- The analysis refuses to mark PASS if even one expected sample is missing, project membership is wrong, PC/NC appear in the included table, or the excluded three cannot be found in P92.
- Generated reports include ASV table, metadata, exclusion audit, diversity, figures and a run manifest; these are saved to timestamped Drive subfolders.

Source code: src/full16s.py, src/subset_analyses.py, src/project_splits.py, **src/fastq_inputs.py**, scripts/run_qiime2.sh.

GitHub Actions: .github/workflows/full-length-16s-ci.yml validates the three Colab configurations, sample-exclusion logic and synthetic smoke tests. Actual scientific processing is executed from Colab, *not* via GitHub Actions.

**Privacy:** FASTQ, vendor archive and patient/sample-level real outputs stay in Drive, never in a public GitHub repository.

## Known outstanding prerequisites for full scientific execution

1. Inspect the vendor ZIP / add individual FASTQs to Drive/raw_fastq. **The raw_fastq Drive folder was empty at last inspection.** If the ZIP does not contain FASTQ the pipeline stops.
2. Enter the real amplification forward primer sequence (5'-3') in each notebook's FORWARD_PRIMER_5TO3. This is required by QIIME 2 dada2 denoise-ccs and is not supplied in the Excel.
3. For taxonomy, add a compatible SILVA feature-classifier `.qza` to Drive/references. No classifier was verified in the Drive folder.
4. Run all three Colabs to produce actual ASV tables and reports. Passing GitHub Actions tests is not evidence that raw analysis has executed.

Reference: https://amplicon-docs.qiime2.org/en/2026.7/references/plugins/dada2/

## Verified primer pair (provided 2026-11-12)

| Primer | 5'-3' sequence | QIIME 2 denoise-ccs option |
|---|---|---|
| 27F | `AGRGTTYGATYMTGGCTCAG` | `--p-front` |
| 1492R | `GYTACCTTGTTACGACTT` | `--p-adapter` |

The primer strings retain the supplied IUPAC ambiguous bases. **The reverse primer is entered in its supplied 5'-3' orientation, not reverse-complemented.** The user-supplied 1492R begins `GYTAC`, whereas some publications describe an `RGYTAC` variant; do not silently add `R`. Check primer-matching retention and DADA2 denoising stats on actual FASTQs. The runner uses a 1000–1600 bp post-primer length window, `maxEE=2`, `max_mismatch=2`, `n_reads_learn=100000` for smaller P18 read sets and creates the required 2026-era base-transition-stats artifact. The actual HiFi dataset has not yet been processed.

References: https://amplicon-docs.qiime2.org/en/2026.7/references/plugins/dada2/ ; https://forum.qiime2.org/t/dada2-denoise-ccs-plugin-error-return-code-1/29320

## Original archive assignment (confirmed 2026-11-13)

**F003 = upper 92 records = P92** and **F004 = lower 18 records = P18**. This is a strict mapping and must never be reversed.

- F003 ZIP: `Result_X209SC26096091-Z01-F003_16S.zip`, Drive ID `1rPpGDmZHDcjNAm0UmjP1kZl5VdGB9478`, 2,170,188,809 bytes. Decompressed 494 files, including 92 primer-containing raw FASTQs (`01.RawData/*/*_withprimer.fastq.gz`) and 92 cleaned FASTQs (`00.CleanData/*/*.fastq.gz`). Drive extraction folder: https://drive.google.com/drive/folders/1tJHfddKf3jlYD-xGJSc7MB_uq9bW8Yyi .
- F004 ZIP: `Result_X209SC26096091-Z01-F004_16S.zip`, Drive ID `1v1FeZMkTKMTmx07sJEZfrY-tzPgVup-0`, 423,220,458 bytes. Decompressed 198 files, including 18 primer-containing raw FASTQs and 18 cleaned FASTQs. Drive extraction folder: https://drive.google.com/drive/folders/1w8tuBjXfrUkGBNHY7kUp80LxusRlfIEq .

For a **fresh DADA2 analysis**, the three Colab notebooks now enumerate only the sample-specific primer-containing FASTQs under their assigned project's `01.RawData` folder recursively, excluding all `00.CleanData` entries. Each notebook checks that its project folder has all **92/18** raw source FASTQs, then downloads only **90/87/16** approved reads. All four controls are dropped before denoising; the three flagged P92 samples are dropped only in the 87-sample variant.

Raw source ZIPs remain unchanged and available in Drive. The separate extraction folders retain original tree structure for audit. Notebook's earlier QIIME 2 micromamba `-f` bug (Markdown link passed instead of YAML file) has been fixed: it now downloads and validates official QIIME 2 environment YAML locally before creating the conda environment.
