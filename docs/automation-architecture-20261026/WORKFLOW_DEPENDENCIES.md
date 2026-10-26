# Workflow Dependencies v1
Date: 2026-10-26. Proposed orchestration; verify actual cron timings from default-branch YAML before declaring these live.

## Directed flow
QQ IMAP (read-only) / SFDC subscribed mail attachments / CSS / Feishu READ → source snapshots → schema+freshness+identity QC → verified relation graph → [invoice actual + payment QC, TAT forecast, NBA] → unified Sheets → authenticated web views. Independently approved outbound changes: action request → human approval & lease → Windows Salesforce UI fill → verify → guarded Save → read-back record ID → Sheets receipt.

## Ordering and triggers
1. QQ ingestion desired 30-minute cadence; incremental UID with high-water mark, avoid gaps after UIDVALIDITY change.
2. SFDC 3-report ingestion: on scheduled poll after report delivery; reuse previously validated staged data when no fresh attachment; prohibit stale version rollback and publish a detailed audit heartbeat.
3. SFDC relation/QQ email evidence audit only after complete valid snapshots; do not close opportunity based on contact/subject overlap.
4. Feishu sync: scheduled READ; materialized outstanding/payment metrics only after source success/freshness check.
5. Invoice/QC → actual revenue fact → month aggregates; project status → forecast month. De-duplicate on invoice IDs before aggregating actual + forecast.
6. NBA refresh after validated source changes; preserve completed/excluded decisions and protect existing formula regions.
7. Publish web read-only views and status only from validated snapshots; otherwise show stale timestamp and last known good result.

## Concurrency, retriability and rollout
- Run one writer per target sheet/range through explicit lease; GitHub concurrency groups alone do not serialize independent workflows.
- On transient failures retry with backoff; no silent green on missing essential inputs; quarantine conflicts; preserve last good data.
- Every run produces run_id, upstream snapshot IDs, inserted/updated/unchanged, quarantined, QC result, duration, and workflow link.
- Planned changes: shadow-only read → offline test → isolated integration → authorized canary → production; no unsupervised write promotion.
- Explicit ownership of each stage, with no destructive overlap between legacy CSS and new workflows.
