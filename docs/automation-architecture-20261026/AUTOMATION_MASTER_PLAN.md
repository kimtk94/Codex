# Automation Master Plan v1
Baseline: 2026-10-26; repository: kimtk94/Codex. Architecture ownership only; no production change implied.

## Scope and score
QQ Mail, CSS, SFDC reports, SFDC Windows UI RPA, Feishu, unified Google Sheets, revenue, NBA and web dashboard. Exactly 50 tracked deliverables. Baseline: 11 done, 27 partial, 12 todo (49% with partial=0.5). This historical status is NOT proof of live acceptance. Status may change ONLY with evidence.

Source of truth: [SFDC_Automation_Followup_2026](https://docs.google.com/spreadsheets/d/1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI/edit). Prior evidence: PR #263 UI RPA, #278-#296 SFDC mail audit/joins, #235 Feishu payment QC, #256 mail reviews, #289 web API. Verify PR merge and operational run separately.

## 50-item ledger
| ID | Domain | Deliverable | Baseline status | Owner | Latest evidence | Acceptance run |
|---|---|---|---|---|---|---|
| A01 | QQ Mail / CSS | QQ IMAP read-only access | done | - | - | - |
| A02 | QQ Mail / CSS | 2025+ source backfill and immutable ledger | partial | - | - | - |
| A03 | QQ Mail / CSS | 30-minute mail ingestion | partial | - | - | - |
| A04 | QQ Mail / CSS | 60-day unanswered evaluation | partial | - | - | - |
| A05 | QQ Mail / CSS | SYSTEM_NOTICE and delegated PC/TS exclusions | done | - | - | - |
| A06 | QQ Mail / CSS | UID exclude/restore decision ledger | done | - | - | - |
| A07 | QQ Mail / CSS | received timestamp backfill/audit | done | - | - | - |
| A08 | QQ Mail / CSS | same-thread response verification | partial | - | - | - |
| A09 | SFDC report intake | Lead/Oppo/Quote parser | done | - | - | - |
| A10 | SFDC report intake | sender and duplicate header handling | done | - | - | - |
| A11 | SFDC report intake | scheduled 3-report staging | partial | - | - | - |
| A12 | SFDC report intake | Lead→Opportunity joins | partial | - | - | - |
| A13 | SFDC report intake | Quote→Opportunity identity joins | partial | - | - | - |
| A14 | SFDC report intake | Active Quote amount validation | partial | - | - | - |
| A15 | SFDC report intake | Opportunity/Quote review queues | partial | - | - | - |
| A16 | SFDC Windows writes | Playwright desktop scaffold | done | - | - | - |
| A17 | SFDC Windows writes | required field selectors | partial | - | - | - |
| A18 | SFDC Windows writes | Account/Contact selected-pill verification | partial | - | - | - |
| A19 | SFDC Windows writes | seven-field batch fill | partial | - | - | - |
| A20 | SFDC Windows writes | existing record Details/Related editor | partial | - | - | - |
| A21 | SFDC Windows writes | maximize and active-window verification | partial | - | - | - |
| A22 | SFDC Windows writes | approved Save→record ID→Sheets writeback | todo | - | - | - |
| A23 | SFDC Windows writes | idempotency and rollback | todo | - | - | - |
| A24 | NBA / follow-up | Lead NBA scoring | done | - | - | - |
| A25 | NBA / follow-up | decision preservation | done | - | - | - |
| A26 | NBA / follow-up | unified candidate pool | partial | - | - | - |
| A27 | NBA / follow-up | Today Top 10 | partial | - | - | - |
| A28 | NBA / follow-up | sent-mail reconciliation | partial | - | - | - |
| A29 | NBA / follow-up | manual done/exclude propagation | partial | - | - | - |
| A30 | NBA / follow-up | P0/P1 autonomous sequencing | todo | - | - | - |
| A31 | Revenue / BI | 2025 official historical basis | done | - | - | - |
| A32 | Revenue / BI | invoice extraction and attribution | partial | - | - | - |
| A33 | Revenue / BI | unissued invoice watch | partial | - | - | - |
| A34 | Revenue / BI | invoice/quote duplicate reconciliation | partial | - | - | - |
| A35 | Revenue / BI | 2025/2026 comparison and 2027 targets | partial | - | - | - |
| A36 | Revenue / BI | formula and bar chart regression | todo | - | - | - |
| A37 | Feishu | read-only Base source | done | - | - | - |
| A38 | Feishu | project TAT forecast | partial | - | - | - |
| A39 | Feishu | user override of forecast month | partial | - | - | - |
| A40 | Feishu | outstanding vs invoice issuance vs receipt | todo | - | - | - |
| A41 | Feishu | bidirectional update contract | todo | - | - | - |
| A42 | Sheets / Web | unified master spreadsheet | done | - | - | - |
| A43 | Sheets / Web | institution/service normalization | partial | - | - | - |
| A44 | Sheets / Web | deprecated tab registry | partial | - | - | - |
| A45 | Sheets / Web | Figma-aligned preview | partial | - | - | - |
| A46 | Sheets / Web | authenticated production dashboard | todo | - | - | - |
| A47 | CI / operations | CI suites and regression | partial | - | - | - |
| A48 | CI / operations | scheduled sync and alerting | partial | - | - | - |
| A49 | CI / operations | end-to-end acceptance | todo | - | - | - |
| A50 | CI / operations | recovery/rollback runbook | todo | - | - | - |

## Ownership
Architecture owner (ChatGPT): data contracts, boundaries, dependencies, acceptance criteria and ledger review. SFDC UI execution agent: authenticated Windows Playwright and controlled writes. Data agent: QQ/SFDC/Feishu ingests, tax invoice and NBA QA. Web agent: secure dashboard and deployment. No agent may claim another team's live test was completed. 

## Status controls
- todo: no proven implementation; partial: design/code/some integration exists but gate incomplete; done: historical completion recognized, not independently accepted.
- A separate accepted=true requires production-compatible evidence (source timestamp, CI run URL, source row reconciliation, user-approval where needed).
- Track status, owner, blocker, PR, SHA, workflow run, checked_at_KST, acceptance evidence and decision log; keep closed items visible.
- Recompute overall score as (done + partial*0.5)/50, separately report strict acceptance percentage.
- Prioritize revenue reconciliation, three-report join QC, NBA decision preservation, UI RPA gates, Feishu freshness, dashboard verification; do not treat issue count as business value.
