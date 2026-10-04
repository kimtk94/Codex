# MasterOS — Obsidian-compatible Knowledge Layer

MasterOS turns the existing Novogene CSS and research estate into a Markdown knowledge graph that can be opened by Obsidian.

## Recommended architecture: no server required

The default runtime is now Google Drive + Colab.

- Google Drive = source files + generated Vault
- Colab = refresh engine
- Obsidian = personal knowledge UI
- GitHub = code/version control
- Vercel = optional read-only web portal later
- Server/SilverBullet = optional advanced mode only

The canonical Drive notebook is `MasterOS_Vault/MasterOS_Colab.ipynb`.

## Source-of-truth policy

- Canonical CSS current state stays in `Novogene_All_Emails`, especially `CSS Project Dashboard`, `CSS Action Center`, `CSS Customer 360`, and `WEB_EXPORT`.
- CSS detailed history/invoice truth stays in `Novogene_CSS/state/css_project_manager.sqlite3`.
- Research snapshots are rebuilt from the research GitHub repositories.
- The Vault is generated and one-way in phase 1: source systems -> Vault.
- Generated Vault fields are never automatically written back to CSS source systems.

The latest raw `project_timeline` event is not always the canonical current project state. The Google Sheet therefore has precedence for current state, while SQLite provides detailed lifecycle history and invoices.

## One-cell Colab workflow

The notebook performs:

1. Mount Google Drive.
2. Authenticate the current Colab Google account.
3. Clone the MasterOS code.
4. Read the canonical CSS Sheet with the signed-in Colab identity.
5. Read `MyDrive/Novogene_CSS/state/css_project_manager.sqlite3`.
6. Generate `MyDrive/MasterOS_Vault/02_CSS`.
7. Clone research repositories.
8. Generate `MyDrive/MasterOS_Vault/01_RESEARCH`.
9. Create minimal Obsidian settings and `08_INBOX`.

No service-account JSON and no always-on server are required.

## Generated Vault

    MasterOS_Vault/
      00_HOME/
        HOME.md
        CSS_DASHBOARD.md
      01_RESEARCH/
        RESEARCH_INDEX.md
        ...
      02_CSS/
        Institutions/
        Customers/
        Projects/
        Services/
        Actions/
          OPEN_ACTIONS.md
          ACT-*.md
      08_INBOX/
      .obsidian/

## Current CSS adapters

`fetch_css_sheet_snapshot.py` supports both:

- Colab/user ADC authentication via `google.auth.default()` (recommended)
- service-account JSON when `--credentials` is supplied (optional server mode)

`css_to_vault.py` combines the canonical Sheet snapshot with `css_project_manager.sqlite3`:

- current stage/progress/customer/attention <- `CSS Project Dashboard`
- action metadata/reason/recommended action/reply drafts <- `CSS Action Center`
- account rollup <- `CSS Customer 360`
- executive KPIs <- `WEB_EXPORT`
- detailed event timeline and invoices <- SQLite

## Research sources

The Colab notebook currently clones:

- `kimtk94/IS_Analysis_V3`
- `kimtk94/brain_research_mr_scrna_seq`
- `kimtk94/Paper_AI_Assistant`

The list is intentionally explicit and can be extended as new research repositories are added.

## Obsidian

Open the synced `MasterOS_Vault` folder as an Obsidian Vault. Generated CSS/research notes should be treated as read-only projections. Personal notes belong in `08_INBOX` or other user-authored folders.

## CI

The GitHub workflow checks Python syntax and the canonical-state regression test. The regression test intentionally gives SQLite a misleading later `Data ready` event while the Sheet says `Completed`, and verifies the generated Vault keeps `Completed`.

## Optional advanced mode

The previous Docker/SilverBullet/server files remain available for a future always-on web editor. They are not part of the default setup and are not required for normal MasterOS use.

## Next extensions

- CKD / IS / Muscle figure and candidate-gene manifests.
- Topic -> service -> institution -> customer relationship graph.
- Vercel read-only executive/search portal.
- Optional approved write-back for tasks/memos only; never free-form two-way database synchronization.
