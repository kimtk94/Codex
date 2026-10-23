# NTIS R&D discovery — phase 1

This branch adds a **manual-only**, read-only collector. No writes to SFDC, Feishu, or Sheets.

1. Add repository Actions secret `NTIS_API_KEY` with the NTIS-issued approval key. Do not put the key in workflow inputs, URLs in logs, or source files.
2. Confirm this key has approved access to **national R&D project search**, not only another NTIS service. Check applicable usage terms, commercial-use permission, rate limits, and IP restrictions before running.
3. Run the Actions workflow **NTIS R&D discovery (manual)** for 2025–2026.
4. Inspect artifact `ntis-rnd-export`: `ntis_projects.csv`, `ntis_sales_candidates.csv`, `ntis_audit.json`.

## Caveats
- Official XML field names may depend on API/version/permissions. This initial integration deliberately preserves all leaf fields in `raw_json`; empty normalized columns require schema mapping based on the first real response.
- `budget_raw` is not normalized and must not be compared across projects until amount unit/field semantics are verified.
- Topic matches are **sales leads for review**, not evidence that an institution needs sequencing or mass spectrometry.
- This version does **not** claim comprehensive coverage: default max 2 pages per keyword/year; pagination and counts must be audited for full backfill.
- Key must not be echoed in any debug output or shared log; API requests are sent over HTTPS. Verify storage/export permissions before publishing results.
- The GitHub Actions artifact is temporary. A Google Sheets/SFDC write-back is a separate stage after schema and identity matching are validated.
