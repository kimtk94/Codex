# HCC Radiomics public-cohort CI

**Scope:** CI metadata readiness audit for `HCC-TACE-Seg` (external public cohort) and `TCGA-LIHC` (radiogenomics matching candidate). WAW-TACE is the proposed training cohort, but downloading its images, deriving radiomics labels, training, and external testing are **not yet implemented**.

- The scheduled/dispatch audit queries the [TCIA NBIA public API](https://wiki.cancerimagingarchive.net/display/Public/NBIA+Search+REST+API+Guide) and exports CT series metadata only.
- Pull requests run an offline fixture test without network calls.
- Workflow artifact contains cohort series CSV and summary JSON; no DICOM data.
- Before training: confirm a single HCC histology, comparable pretreatment acquisition phases, distinct patients, compatible segmentation and feature definitions, and a patient-level split. Avoid leakage through repeated series or lesions.
- Training: WAW-TACE; external public test: HCC-TACE-Seg; hospital external test: pending approved data. TCGA-LIHC: exploratory gene-expression associations, only for cases with verified matched IDs.
- Never upload identifiable hospital DICOM, linkage tables or genomic data to public GitHub Actions. Use approved secure compute for controlled hospital data.

Use Actions → **HCC Public Cohort Audit** → Run workflow. Inspect the downloadable `hcc-tcia-cohort-audit` artifact.
