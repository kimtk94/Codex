# Genixcure PCR short-read reanalysis — Orientation / primer-end audit

**Status (2026-11-04):** Verified QC+primer reanalysis completed for PCR_6_13, Brain_1–3, Motor_1–3, SH_SY5Y_1: **8/11**. Remaining: SH_SY5Y_2, SH_SY5Y_3, Input. A subfolder for SH_SY5Y_2 exists but contains no completed files.

**Source:** Verified, existing `PCR_11_Reanalysis_QC_v2/{sample}/{sample}_single_end_unique.csv.gz` files in Google Drive. This audit only used the **seven Brain/Motor/SH_SY5Y_1 samples** and does not conflate them with PCR_6_13, which has a different confirmed primer detection profile.

## Primary observations

- `PCR_6_13`: **13,481,009 / 14,538,899 (92.7%)** QC merged reads had both provided AAV primer ends; **3,788,424** unique and **1,486,271** singleton sequences remained in its `both_end` category. Follow up as a separate construct/design group.
- In Brain/Motor/SH_SY5Y_1, both provided AAV primers were detected on **0%** of merged reads; most reads matched one AAV F primer end. Example Brain_1: **5,607,309 right_RC_F** and **5,291,688 left_F** reads, based on its sample summary.
- Inspection of *paired ends on the same trimmed sequence*, not merely marginal motif frequencies, finds recurring opposite-orientation pairs:
  - `A...reverse_complement(B)` with **A = CGCGATATATCGTGTACAAG**, **B = ACCTTCCATCGATAAGGAAG**
  - `B...reverse_complement(A)`
  - Across seven samples, **60,443,725 / 71,270,628 (84.8%)** of single_end reads fell in these two exact 20-mer pairing classes.
  - These are compatible with opposite orientations of an amplicon or a construct junction. **They do not establish that A or B is a primer**, or confirm hairpin biology or plasmid identity.

## Exploratory exact reverse-complement canonicalization

For each individual unique `sequence`, compute `min(sequence, reverse_complement(sequence))` and sum its original `read_count`. Applied **within the `single_end` category and separately within each sample**. It does not merge different-length reads, mismatches, trimmed categories, or different samples.

| Sample | Single-end reads | Original unique | RC normalized unique | Reduction (%) | Opposing motif pair (%) |
|---|---:|---:|---:|---:|---:|
| Brain_1 | 10,898,997 | 120,938 | 102,865 | 14.9 | 61.9 |
| Brain_2 | 8,315,535 | 114,240 | 98,212 | 14.0 | 71.3 |
| Brain_3 | 9,584,968 | 57,091 | 47,126 | 17.5 | 84.5 |
| Motor_1 | 10,728,321 | 67,269 | 57,869 | 14.0 | 93.0 |
| Motor_2 | 11,058,258 | 91,115 | 80,109 | 12.1 | 92.3 |
| Motor_3 | 11,205,422 | 104,121 | 92,835 | 10.8 | 93.9 |
| SH_SY5Y_1 | 9,479,127 | 94,257 | 84,439 | 10.4 | 94.5 |
| **Total (sum across samples)** | **71,270,628** | **649,031** | **563,455** | **13.2** | **84.8** |

## Interpretation and data integrity

1. Exact orientation canonicalization removed **85,576 / 649,031 (13.2%)** unique categories in the seven-sample diagnostic. **All 71,270,628 weighted reads were retained.**
2. The large relative difference between PCR_6_13 (both ends match) and the seven other samples (one end matches) is a **sample design / library architecture investigation trigger**, not evidence that the other seven libraries are invalid.
3. The current category-specific counts do not recover the original molecules: no UMI-based deduplication was performed, and exact reverse-complement sequences alone do not distinguish biological variants from sequencing or PCR errors.
4. Quality filtering in the latest reanalysis reduced PCR_6_13's merged reads from **14,567,586 to 14,538,899** (loss **28,687**); its original 6,335,288 unique count cannot be compared with primer-trimmed `both_end` without accounting for read selection and category changes.

## Required next steps

- Complete raw FASTQ reanalysis for **SH_SY5Y_2, SH_SY5Y_3, Input** using the previously saved Colab v4 (`RUN_ONLY_PCR_6_13=False`, `OVERWRITE=False`). No GitHub Action can access private Drive FASTQ without configured Drive credentials.
- Obtain/verify the actual complete sequencing construct or amplicon design (including the second primer, index and flanking sequence). Align representative read termini against the construct; do not force `both_end` by artificially redefining primers based only on high-frequency terminal motifs.
- After the remaining 3 samples complete, rerun `Genixcure_Primer_Orientation_Audit.py` (or the companion Colab) on all 10 Brain/Motor/SH_SY5Y/Input samples and compare remaining unique/singleton distributions.

**Original data are preserved.** This report is read-only and does not replace or reclassify the output CSVs.
