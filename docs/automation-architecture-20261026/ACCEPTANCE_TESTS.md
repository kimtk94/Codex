# Acceptance Tests v1
Date: 2026-10-26. PASS requires linked actual artifact; code presence alone is insufficient.

| Gate | Test | Proof |
|---|---|---|
| SRC-01 | QQ incremental coverage, UID restart, 60-day unanswered and PC/TS/SYSTEM_NOTICE exclusions | counts, gap check, nonmutating replay |
| SRC-02 | Lead/Oppo/Quote identify newest compatible valid source and preserve prior staged when no new report | report timestamps + SHA, Google Sheet audit |
| ID-01 | Lead-conversion, Quote/Oppo, Account/Contact joins; no name-only identity link | unmatched counts, sampled exact-ID review |
| FIN-01 | All 2025 and current 2026 invoice coverage audited separately from official USD basis | month×source comparison, confirmed missing periods |
| FIN-02 | Confirm invoice dedup and quote/forecast no double counting | independent invoice sum reconciles monthly actual |
| FIN-03 | Unissued/watch and Outstanding/paid remain distinct; invoices with 0 matches surfaced | review queue evidence and negative cases |
| NBA-01 | Manually done/excluded/sent leads remain suppressed after three consecutive refreshes | before/after UID snapshot diff |
| TAT-01 | Forecast per status and owner override propagates to selected month + totals | user override round trip + sum controls |
| RPA-01 | Authenticated Chrome + window/record verified, lookup pill and affiliation verified, all 7 fields readback | UI evidence without credentials |
| RPA-02 | Authorized single Save obtains exact SFDC ID and Sheets receipt; replay creates zero duplicates | approved sandbox/test scope, audit output |
| WEB-01 | Allowed user sees live validated data; unauthorized user denied; stale-data warning | preview URL, auth tests, source timestamp |
| OPS-01 | 30-min mail schedule, SFDC report dependency, Feishu refresh, failure/restore alert and lock | three successful consecutive scheduled runs + injected error |
| OPS-02 | E2E safe replay leaves existing manual decisions, 2025 facts, and invoice records unchanged | snapshot diff + GitHub workflow URL |

## Evidence and acceptance
A gate passes only after recording: gate ID, expected vs observed, source snapshot UTC/KST, run URL, SHA, test owner, approval date, blockers. Green CI without reading real source is NOT operational PASS. Never auto-mark the 50 tasks complete from mere PR existence.
