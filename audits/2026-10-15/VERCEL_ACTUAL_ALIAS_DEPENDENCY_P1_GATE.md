# Kalman 32nd audit — actual production alias routing & multi-site release gate
Date: **2026-10-15 KST**

**FINAL STATUS: ALIAS_RECONCILIATION_PASS / 203_OFFLINE_TESTS_PASS / P1_PRODUCTION_RELEASE_HOLD**

## Scope and provenance
- GitHub: only `kimtk94/Codex@audit/kalman-control-20261014` audit source, tests and documentation changed.
- Vercel: **GET-only** `get_alias`, `get_deployment` by both ID and hostname, `list_deployment_files`, and `get_deployment_file_contents` for limited public application configuration files.
- Desktop Commander device `taehoonserver` was **online** but **monthly usage limit prevented any filesystem or runtime command**. Do **not** state the running server SHA, imported module version or current service health has been verified.
- No broker account read/write, live trading, Neon DML, Vercel deployment/promotion/alias change, or LIVE server change.

## Critical correction: aliases, not newest READY builds, determine the active sites
Vercel `list_deployments` / `get_deployment(id)` may return the newest READY deployment and its apparent alias field; this is **NOT authoritative** for which deployment a user-facing alias currently points to. We independently resolved each user-facing hostname by `get_alias` AND `get_deployment(idOrUrl=hostname)`; they agreed:

| Production hostname | Actual alias deployment | Source | Notes |
|---|---|---|---|
| `kalman-investment-hub-v2.vercel.app` | `dpl_BJDfGryiDg2Z5AdQvVYNG9GqeV8L` | **CLI** | 42 source/build tree entries, including `src/api/assets.js`, `src/api/health.js`, `src/app.js`, and `src/vercel.json` |
| `kalman-investment-hub-us.vercel.app` | `dpl_FkCb25iWLwiQVy6EAk6eXxLFZAix` | **CLI** | Its latest READY CLI deployment ID differs; active alias has `src/api/market-kpis.js` but not a local `src/api/assets.js` |
| `kalman-investment-hub-kr.vercel.app` | `dpl_HuDFT3yJrSjfpC63ZYDknB58ixkK` | **CLI** | Deployed `src/vercel.json` recovered and decoded |
| `kalman-investment-hub-v2-staging.vercel.app` | `dpl_8V5GjXVpU2tEixvcNEh6hwKiY32C` | Staging deployment | Separate older site; NOT latest audit-branch built package |

For comparison, the main project's more recent READY Git deployment `dpl_CYit6nBjGeR4ghkmPHE7ksNKUF68` is associated with `kimtk94/IS_Analysis_V3@2615e63e3b3c31014ea75e99b88e81b871f76ba3`, **but it is NOT the active main hostname's alias deployment**. That corrects an earlier overbroad inference. Separately, authenticated Vercel Git connection remains incorrectly linked to `kimtk94/IS_Analysis_V3`. It is a **potential future auto-deploy contamination risk**, not proof that current site serves research code.

## Critical graph: both US and KR depend on shared MAIN API
Retrieved the **actual active deployed** `src/vercel.json` contents from Vercel for both US and KR sites. Both include:
```json
{"source":"/api/:path*","destination":"https://kalman-investment-hub-v2.vercel.app/api/:path*"}
```
They also locally rewrite `/market-pulse` to `/api/market-kpis`.

Consequences:
- MAIN alias or `/api/assets` behavior changes can affect **MAIN + US + KR** simultaneously.
- `US` and `KR` latest deployments are NOT sufficient to verify real API behavior; the shared main alias must be verified.
- A source change in main needs a coordinated three-site GET-only smoke test and a rollback plan capturing exact pre-change alias IDs.
- Project-level route API returned empty route arrays previously; that does **not** negate routes from the deployment's `vercel.json`.

## Actual-served-code verification limitations
- The main active CLI deployment file tree IS available (contrary to latest wrong-repo Git deployment file-tree 404).
- Its `src/vercel.json` was fully retrieved and showed local API dashboard/account rewrites.
- `src/api/health.js` full content was **truncated by connector output limit**, as were larger application JS files; do not assert verified active `v7.4.36` release version or current frontend net masking based only on a partial prefix.
- Real `/api/health` and `/api/assets` HTTP responses, brokerage state, production source hash, and current runtime imported code version have NOT been independently attested.
- No credentials, emails, or sensitive account fields are stored in the audit snapshot.

## New audit-only artifacts and executable gates
1. `audits/2026-10-15/vercel_actual_alias_snapshot.json` — sanitized four-domain alias deployment matrix, source types, US/KR rewrites, wrong Git link and unresolved evidence flags.
2. `audits/2026-10-14/quality/vercel_alias_dependency_gate.py` — pure fail-closed contract:
   - must list exactly four known sites with explicit project/deployment IDs
   - both US/KR API rewrites must resolve to fixed MAIN origin
   - compares refreshed aliases to pinned prior baseline to identify drift
   - MAIN alias change flags MAIN+US+KR as impacted, preventing one-site-only acceptance
   - wrong main Git repository, unverified runtime JS, unverified cross-site smoke, fee/position evidence or missing operator approval returns PRODUCTION_HOLD
   - even a purely hypothetical fully passed preflight returns `release_authorized:false`; no script executes deployment
3. `audits/2026-10-14/quality/test_vercel_alias_dependency_gate.py` — 14 tests covering actual connected alias snapshot, main vs newest Git distinction, both rewrites, missing domains, drift blast radius, wrong source, missing attestations and non-authorizing positive case.
4. Existing `hub_offline_release_gate.py` still rebuilds complete `vNext.7.4.36` and enforces API/UI **NULL/검증 전** masks for known P1 stale net returns in the *candidate package only*. Candidate is **NOT the current live site**.

## CI evidence
GitHub Actions run: https://github.com/kimtk94/Codex/actions/runs/38657530013
- **188 offline unittest methods PASS** (includes 1,000 seeded positive and 2,000 mutated negative scenarios nested inside two methods).
- **15 disposable PostgreSQL actual-process mirror integration methods PASS**.
- **203 total unittest methods PASS**.
- Complete 30-file `vNext.7.4.36` bundle: `api_net_return_masked:true`, `ui_net_evidence_guard:true`, `web_read_only_contract:true`, `release_authorized:false`.
- All validation ran without deploying a site or changing any Production alias.

## Release and rollback gates (NOT YET APPROVED)
1. Freeze live MAIN/US/KR/STAGING alias mappings above immediately before any authorized change; check direct hostname resolution a second time. Stop if drifted.
2. Confirm the actual served MAIN HTML/JS and version; do not rely on connected Git repository metadata or newest READY release list.
3. Confirm the desired Git-link policy separately: move away from unintended research repo link or explicitly disable that source's automatic pushes. Requires operator approval.
4. Stage the exact known-good candidate web bundle on a separately authorized isolated staging site. **Do NOT run the older `deploy_investment_hub_v7436_ci.sh` as a dry run**; it does `vercel deploy --prod --skip-domain` AND `vercel promote`.
5. For MAIN and US/KR downstream: smoke test `/api/health`, `/api/assets?view=control`, `/api/account` GET-only, expected schema/status, no order endpoints activated, account-data redaction and all unverified net returns masked.
6. Broker statement and fee-currency evidence remain necessary before treating any net return as independently verified. The five inflated historical Neon net-return fields are **NOT fixed**.
7. Capture rollback IDs, perform an explicitly approved alias cutover only after all acceptance gates; rollback if mismatch. LIVE trading engine code must remain independently frozen.

**DECISION: NO PRODUCTION RELEASE OR ALIAS CHANGE.**
