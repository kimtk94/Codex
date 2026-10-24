# Sales Command — Data Integration Contract

**State:** read-only source schema verified, runtime wiring NOT yet enabled.

## Verified sources
- Central workbook: `SFDC_Automation_Followup_2026`
- Revenue recognized basis: Tax Invoice, dual units KRW and K USD, reporting FX 1 USD = 1,500 KRW.
- `BI Monthly KPI`: `Metric | Value | Unit`. Do not assume every metric is period-specific.
- `BI Service Monthly 10`: `Invoice Month | Service Group | Invoice Count | Revenue KRW | Revenue K USD | Coverage | Invoice Source | Reporting FX | Validation`.
- `BI Revenue Fact`: `Invoice Number | Invoice Month | Invoice Date KST | Institution | Service L4 | Service Group | Revenue KRW | Revenue K USD | AMEA Project ID | H Project ID | Classification | FX KRW/USD | Source`.
- `BI Followup Unified`: `Priority | Source | Record ID | Institution | Customer | Project ID | Service | Issue / Type | Recommended Action | Original Status | Due / Event Date | Age Days (Source) | Source Updated At | Freshness | Responsible Owner | Source Tab | Evidence ID | Dedup Key | Latest CSS Stage | Latest CSS Event | Resolution Evidence Audit`.
- QQ workbook `Novogene_All_Emails`: `Unanswered Emails Auto` with waiting days, sender, subject, owner, reply status and last checked timestamp.

## Safety and correctness rules
1. The browser MUST NOT call private Google Sheets directly with service-account credentials. Run a permission-checked server-side adapter or CI-produced access-controlled summary.
2. No customer-level details, names or addresses in static/public preview assets. Limit exports to approved aggregated statistics.
3. Incomplete 2025 coverage: `PARTIAL_2025_BACKFILL` must show a prominent coverage annotation.
4. Classifications `PROVISIONAL` / `REVIEW` are not audited sales facts. Display review markers.
5. An unverified fetch, stale cache, or missing sheet must display `Data unavailable`, not a fabricated zero.
6. All APIs must return the dataset as-of timestamp and source tab names.
7. No outbound QQ mail or Salesforce write from dashboard. Read-only by default.
8. Future live adapter must have authorization checks, bounded queries, secret handling, error paths and tests.

## Proposed read-only API
`GET /api/sales/overview?from=2025-01&to=2026-10`

Response object:
```json
{
  "asOf": null,
  "coverage": "unverified",
  "revenue": {"krw": null, "kUsd": null, "basis": "TAX_INVOICE"},
  "serviceMonthly": [],
  "followupSummary": [],
  "sourceTabs": ["BI Monthly KPI", "BI Service Monthly 10", "BI Followup Unified"]
}
```

No live endpoint was deployed by this PR. Wire this contract only after identifying the existing CSS frontend and authentication boundaries.
