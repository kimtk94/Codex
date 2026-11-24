# Feishu sales automation

This directory contains the active sales-data integrations, derived Feishu
tables, native dashboards, and validation tools. The integration has progressed
beyond the original read-only P0 probe: scheduled workflows publish verified
source-owned data to the sales workspace.

Start with [the architecture and operating guide](ARCHITECTURE.md) for ownership,
data flow, execution locks, validation boundaries, and efficiency work.

## Main entry points

| Responsibility | Workflow | Implementation |
| --- | --- | --- |
| SFDC reports, Quote Review, and Weekly KPI | [SFDC Three Report Mail Digestion](../../.github/workflows/sfdc-three-report-email-digestion.yml) | [report ingestion](../sfdc/three_report_email_ingest.py), [scoped metrics](sales_metrics_sync.py) |
| Feishu source mirrors, Payment/project boards, and Monthly Revenue | [Sources Payment Online Monthly Unified](../../.github/workflows/feishu-sources-unified.yml) | [source sync](project_status_sync.py), [scoped metrics](sales_metrics_sync.py), [monthly publication](monthly_revenue_actual_sync.py) |
| QQ mail staging and audit | [QQ Mail Feishu Sync](../../.github/workflows/qq-mail-feishu-sync.yml) | [mail ingestion](qq_mail_ingest.py), [mail audit](qq_mail_audit.py) |
| Quotation detail and reference index | [Quote Report Email Sync](../../.github/workflows/feishu-quote-report-email-sync.yml) and the SFDC pipeline's mirror job | [report bridge](sfdc_quote_report_bridge.py), [reference index](sfdc_quote_reference_preindex.py) |
| Navigation and native presentation | [Native Sales Home](../../.github/workflows/feishu-native-sales-home.yml) and the relevant dashboard workflows | [home](sales_native_home.py), [trends](sales_native_trends.py), [native charts](native_dashboard_cli.py) |

## Configuration and execution

Workflow files define the credentials, supported inputs, and execution gates for
each integration. Feishu clients use `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and
`FEISHU_BASE_APP_TOKEN`; Sheets readers use `GCP_SERVICE_ACCOUNT_JSON`. Mail
credentials are defined in the mail workflows. Never commit credentials or emit
customer records in test fixtures, logs, or artifacts.

The production sales workspace token is checked by the relevant writers. A wiki
node, table ID, and view ID are not interchangeable with a Base app token.

For `sales_metrics_sync.py`, `FEISHU_METRIC_MODE=plan` reads and validates sources
without writing; `apply` permits bounded, source-owned upserts.
`FEISHU_METRIC_SCOPE=quote|operations|all` controls record ownership. Source and
schema/view validation are broader than record scope; see the architecture guide
before changing these boundaries.

PR paths run offline checks and exclude live jobs through workflow gates. Use a
workflow's documented manual inputs for a deliberate operational run. A green PR
check establishes code validation, not source freshness or successful publication.

## Read-only diagnostics and recovery

The original [Base Readonly Probe](../../.github/workflows/feishu-base-readonly.yml)
remains a diagnostic. It does not describe the capabilities of this whole
directory. Legacy standalone workflows also remain available for deliberate
recovery; their automatic triggers are disabled by ownership contract tests.

To diagnose failed publication, inspect the failing stage and its sanitized source
and sink evidence. An unrelated successful probe, skipped job, or successful mail
fetch does not prove that downstream data was refreshed.
