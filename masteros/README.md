# MasterOS — Obsidian-compatible Knowledge Layer

MasterOS turns Novogene CSS and research outputs into a Markdown knowledge graph that can be opened directly by Obsidian.

## Default architecture: no server required

- **Google Drive** = source files + generated Vault
- **Colab** = refresh engine
- **Obsidian** = personal knowledge UI
- **GitHub** = code/version control
- **Vercel** = optional read-only portal later
- Server/SilverBullet = optional advanced mode only

The recommended notebook is `MasterOS_Vault/MasterOS_Colab_v2.ipynb`.

## Source-of-truth policy

- CSS current state: `Novogene_All_Emails` → `CSS Project Dashboard`, `CSS Action Center`, `CSS Customer 360`, `WEB_EXPORT`
- CSS lifecycle/invoices: `Novogene_CSS/state/css_project_manager.sqlite3`
- CKD research results: `MyDrive/IS_Analysis_V3/results/ckd`
- Public research documentation: GitHub `kimtk94/IS_Analysis_V3`
- Vault: generated projection only; source systems remain authoritative
- Phase 1 is one-way: **source systems → Vault**

## v2 normalization

`css_to_vault.py` now normalizes common account aliases before building the graph. Examples:

- `Ehwa Univ.` / `Ehwa Woman University` → `Ewha Univ.`
- `Kyungpook Univ.` / `Kyungpook University` → `Kyungpook National Univ.`
- `KAIST Univ.` → `KAIST`
- `Aginglab` → `AgingLab`
- `GNU` → `Gyeongsang National Univ.`
- `Rokit Genoics` → `ROKIT Genomics`
- numeric parser artifacts are recovered when the project description has a clear institution, e.g. KIOM and University of Missouri

A generated `00_HOME/NORMALIZATION_REPORT.md` records every observed merge.

## v2 service taxonomy

Existing structured service labels are preserved. Legacy `Other` and generic `WGS` are reclassified from the project description.

Key categories include:

- mRNA-Seq
- PMP / PML
- Amplicon
- Proteomics / Metabolomics
- Microbial WGS
- Human WGS
- Plant WGS
- Animal WGS
- WGS - Unclassified
- RIP-Seq / ChIP-Seq / RRBS / Hi-C
- small RNA-Seq / lncRNA-Seq
- EPIC Array
- Special Shipment

This avoids silently rewriting an already-correct `mRNA-Seq` project just because a mixed project description also contains another assay.

## CKD Drive ingestion

`drive_research_to_vault.py` reads `MyDrive/IS_Analysis_V3/results/ckd` directly. It does not require the research server.

It generates:

    01_RESEARCH/CKD/
      CKD_MASTER.md
      Stages/
        stage1.md
        stage2.md
        stage2b_coloc.md
        stage2c_susie.md
        stage3a_kidney.md
        stage3b_celltype.md
        ...
      Candidates/
        ACP1.md
        CPVL.md
        ...
        UMOD.md

Stage notes inventory all result files and preview small summary/QC/evidence artifacts. CKD candidate notes are **seeded only from `stage2/stage2_candidates.tsv`** (or, if that file is unavailable in a future freeze, an explicit thesis-ready candidate table). Coloc, SuSiE, kidney and integrated-evidence tables may add evidence only for those seeded genes. This prevents large kidney expression/eQTL tables from creating hundreds of off-target candidate nodes.

## One-cell Colab v2 flow

1. Mount Google Drive and authenticate the current Google account.
2. Clone `kimtk94/Codex` main.
3. Read canonical CSS Sheet.
4. Read CSS SQLite directly from Drive.
5. Normalize institutions/services and regenerate `02_CSS`.
6. Clone the public `IS_Analysis_V3` repo for research documentation snapshots.
7. Read every top-level CKD result directory directly from Drive, including Stage4/KoGES/thesis-ready directories when they are synced there.
8. Regenerate CKD stage notes and the seed-restricted candidate panel; stale candidate notes are deleted on every refresh.
9. Write coverage warnings in `CKD_MASTER.md` when Stage4 EAS, KoGES or thesis-ready outputs are not yet present in Drive.
10. Update the Obsidian Vault.

No service-account JSON and no always-on server are required.

## Generated Vault

    MasterOS_Vault/
      00_HOME/
        HOME.md
        CSS_DASHBOARD.md
        NORMALIZATION_REPORT.md
      01_RESEARCH/
        RESEARCH_INDEX.md
        IS_Analysis_V3/
        CKD/
      02_CSS/
        Institutions/
        Customers/
        Projects/
        Services/
        Actions/
      08_INBOX/
      .obsidian/

`02_CSS` is treated as fully generated and is rebuilt each refresh so stale alias/service files disappear. Personal notes should live outside generated folders, preferably `08_INBOX`.

## CI

MasterOS CI checks Python syntax and regression tests for:

- canonical Sheet state overriding misleading later SQLite events
- institution alias normalization
- service taxonomy behavior
- CKD candidate-note generation restricted to the explicit stage2 seed panel
- stale CKD candidate pruning across refreshes

## Next extensions

- IS/CKD/Muscle figure manifests
- Research topic → service → institution → customer graph edges
- customer/research matching scores
- optional Vercel read-only portal
- approved task/memo write-back only, never unrestricted two-way DB synchronization