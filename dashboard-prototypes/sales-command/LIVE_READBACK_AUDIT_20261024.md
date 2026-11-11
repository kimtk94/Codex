# Live Google Sheets Readback Audit — 2026-10-24

Read-only inspection through the connected Google Drive integration.

## Source
- Central workbook: `SFDC_Automation_Followup_2026`
- `BI Monthly KPI` rows: Invoice Revenue = 1,172,375,600 KRW; Invoice Revenue K USD = 781.5837333; Invoice Count = 327; Classification Review = 33; FX = 1,500 KRW/USD.
- `BI Service Monthly 10`: 120 service-month rows, 12 distinct months.
- Sum `Revenue KRW` across the 120 service-month rows: 1,172,375,600 KRW, **matching** KPI exactly.
- Month field validation: no invalid YYYY-MM strings in inspected rows.
- Coverage labels: `PARTIAL_2025_BACKFILL` (20 rows), `SOURCE_COVERAGE_CHECK` (90 rows), `MONTH_TO_DATE` (10 rows).
- KPI historical coverage: `PARTIAL`, notes `2025 Jan-Oct pending QQ backfill`.

## Interpretation
This is a one-time authenticated connector read, NOT successful authentication by the Python adapter.
This confirms numerical consistency of the two sheets, NOT completeness of 2025 or invoice-level correctness.
Avoid publishing private record detail or authenticated workbook URLs to public dashboards.

## Release gate
1. Confirm an authorized short-lived Google Sheets access token/identity is usable in a secure CI run.
2. Exercise adapter on live Sheets, compare generated totals with the 1,172,375,600 KRW readback (allowing for source updates).
3. Validate output retention and hosting authorization; never publish customer-level rows.
4. Surface `PARTIAL_2025_BACKFILL`, `SOURCE_COVERAGE_CHECK`, and `MONTH_TO_DATE` notices in UI.
5. Require browser rendering test, then review before deployment.
