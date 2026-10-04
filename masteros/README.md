# MasterOS — Obsidian-compatible Knowledge Layer

MasterOS turns the existing Novogene CSS and research estate into a Markdown knowledge graph that can be opened by Obsidian and served in a browser by SilverBullet.

## Source-of-truth policy

- Canonical CSS current state stays in the existing `Novogene_All_Emails` Google Sheet, especially `CSS Project Dashboard`, `CSS Action Center`, `CSS Customer 360`, and `WEB_EXPORT`.
- CSS detailed history/invoice truth stays in `css_project_manager.sqlite3`.
- Research truth stays in `/srv/is-analysis` repositories and result folders.
- Google Drive is sync/backup and document storage.
- The Vault is a generated knowledge layer. Phase 1 is one-way: source systems -> Vault.
- Generated Vault fields are never written back into CSS source systems automatically.

This split is intentional: the latest raw `project_timeline` event is not always the canonical project state. The Sheet dashboard can, for example, mark a project `Completed` even if a later informational `Data ready` event exists. MasterOS therefore gives the Sheet precedence for current project state and uses SQLite for lifecycle history and invoices.

## Generated Vault

    00_HOME/
      HOME.md
      CSS_DASHBOARD.md
    01_RESEARCH/
      RESEARCH_INDEX.md
      ... generated research snapshots
    02_CSS/
      Institutions/
      Customers/
      Projects/
      Services/
      Actions/
        OPEN_ACTIONS.md
        ACT-*.md

Project notes link to institution, customer, service and recent lifecycle events. Institution, customer and service notes backlink to their projects, so Obsidian/SilverBullet graph navigation works without copying every source email into Markdown.

## Current CSS adapters

`fetch_css_sheet_snapshot.py` reads the canonical Google Sheet read-only and caches the four required tabs as JSON.

`css_to_vault.py` combines that snapshot with `css_project_manager.sqlite3`:

- current stage/progress/customer/attention <- `CSS Project Dashboard`
- action metadata/reason/recommended action/reply drafts <- `CSS Action Center`
- account rollup <- `CSS Customer 360`
- executive KPIs <- `WEB_EXPORT`
- detailed event timeline and invoices <- SQLite

If the Sheet snapshot is unavailable, the converter can still create a conservative SQLite-only fallback Vault, clearly labeled as fallback.

## Server install

1. Clone this repository to `/srv/masteros/repo`.
2. Copy `masteros/config/masteros.env.example` to `/srv/masteros/.env` and change `SB_USER`.
3. Configure an rclone Google Drive remote named by `RCLONE_REMOTE`.
4. Create a read-only Google service-account JSON at `/srv/masteros/secrets/google-service-account.json` and share the CSS Sheet with that service account as Viewer.
5. Load the environment and run the bootstrap script.

Example:

    cd /srv/masteros/repo
    cp masteros/config/masteros.env.example /srv/masteros/.env
    . /srv/masteros/.env
    bash masteros/scripts/bootstrap_server.sh

SilverBullet binds only to `127.0.0.1:3000`. Put HTTPS/authenticated reverse proxy or a private tunnel in front of it; do not expose the raw port publicly.

SilverBullet uses the same Markdown folder at `/srv/masteros/vault`. Obsidian can open a synced copy of `MasterOS_Vault` from Google Drive on desktop/mobile.

## Routine sync

    . /srv/masteros/.env
    bash /srv/masteros/repo/masteros/scripts/sync_all.sh

Suggested cron after validation:

    15 * * * * . /srv/masteros/.env; bash /srv/masteros/repo/masteros/scripts/sync_all.sh >> /srv/masteros/masteros_sync.log 2>&1

## CI

The GitHub workflow checks Python syntax and runs the canonical-state regression test. The regression test intentionally gives SQLite a misleading later `Data ready` event while the Sheet says `Completed`, and verifies the generated Vault keeps `Completed`.

## Next extensions

- Research result/figure manifests from CKD, IS, metabolic resilience and muscle pipelines.
- Vercel read-only executive dashboard fed from the same generated manifest.
- Optional approved write-back for tasks/memos only; never free-form two-way DB synchronization.
