# Kalman 31st audit — Full Investment Hub build-only preflight and Vercel multi-site routing

**Date:** 2026-10-15 KST  
**Decision:** `189_TESTS_PASS / FULL_WEB_BUILD_PASS / P1_PRODUCTION_RELEASE_HOLD`

This document records connected Vercel read-only inspection, full real builder execution inside GitHub Actions, and downstream web-risk evidence. No live broker request, order, Production Neon DML, Vercel deployment, Git-link change, server edit or main-branch merge occurred.

## 1. The complete v7.4.36 web build is reproducible, fully offline
- Kalman web source provenance: `kimtk94/Codex`, audit branch `audit/kalman-control-20261014`.
- `kalman-hub-recovery/v7.4.23/source_manifest.ndjson` is a pinned **30-file** bundle. Starting from it, `build_investment_hub_v7424_execution_telemetry.py` and successive historical generators through `build_investment_hub_v7436_shadow_freshness.py` rebuild the latest `vNext.7.4.36`.
- New pure audit gate: `audits/2026-10-14/quality/hub_offline_release_gate.py`.
  It runs the ENTIRE builder chain in GitHub Actions, verifies the strict 30-path allowlist, decodes all final files, checks read-only web configuration and version, enforces UI and API P1 net-return masks in **final app.js + api/assets.js**, and node-syntax-checks app, assets API and health API. It emits a compact JSON report of SHA256 hashes for selected JS/index/vercel config, no source blob or credentials. Never invokes `vercel` or touches a deployed site.
- `test_hub_offline_release_gate.py` includes normal/mutated manifest tests, unprotected API/UI cases and path-traversal/duplicate protections.
- Existing Vercel deployment script `kalman-toss-gateway/scripts/deploy_investment_hub_v7436_ci.sh` is **NOT a harmless dry-run**: it runs `vercel deploy --prod --skip-domain` and later `vercel promote`. It was NOT invoked. To rehearse without production effects use the dedicated build-only gate, not the deploy script.

### API protection added on audit branch only
- Historical builder `build_investment_hub_v7424_execution_telemetry.py` previously read the raw `net_return` and `round_trip_cost_bps` directly from the Production `v_live_trade_ledger` view, which still contains five known P1 multi-entry P&L overstatements.
- Until broker-verified independent evidence exists, the candidate generates typed SQL values
  `NULL::numeric AS net_return` and `NULL::numeric AS round_trip_cost_bps`.
  `realized_return_pct` (gross price-only fraction) remains available.
- The final generated JS UI already hides all net values absent four explicit independent evidence flags and shows `검증 전`. This new API-level mask prevents raw known-bad numbers from being returned by this query, not merely hidden in the browser.
- **By design all candidate net returns are masked**, including otherwise correct single-leg entries; this is safer than claiming unsupported profit. It is NOT a real broker fee reconciliation and may need a separately approved verification source for restoring net performance.
- The offline gate expressly rejects a final bundle reverting to raw `realized_return_pct,net_return,round_trip_cost_bps` projection.

## 2. Full CI evidence
**GitHub Actions run:** https://github.com/kimtk94/Codex/actions/runs/38656568308 — COMPLETED / SUCCESS.

- 174 offline unittest methods OK, including prior 1,000 positive Decimal reference scenarios and 2,000 fail-closed mutated scenarios nested in two test methods.
- 15 disposable PostgreSQL full mirror pipeline test methods OK.
- **189 unittest methods total** (separate from 3,000 seeded evaluations).
- Full build executed latest version: `vNext.7.4.36`.
- Log result: `manifest_files:30`, `api_js_files:12`, `ui_net_evidence_guard:true`, `api_net_return_masked:true`, `web_read_only_contract:true`, `release_authorized:false`, `decision:OFFLINE_BUILD_PASS_RELEASE_HOLD`.
- GitHub Actions artifact includes `hub_offline_build_report.json` with hashes and `quality_report.json`. These are audit artifacts, not deployment authorization.

## 3. Verified Vercel project/source matrix (read-only)
| Vercel project | Deployment mechanism / artifact | Grounded risk |
|---|---|---|
| `kalman-investment-hub-v2` | Current **Git link** `kimtk94/IS_Analysis_V3`. READY Production `dpl_CYit6nBjGeR4ghkmPHE7ksNKUF68` Git metadata `IS_Analysis_V3@2615e63e3b3c31014ea75e99b88e81b871f76ba3`; project alias `kalman-investment-hub-v2.vercel.app` | **WRONG SOURCE / AUTO-DEPLOY CONTAMINATION RISK.** Git commit tree has no Kalman web app. Deployment file tree endpoint returns 404; actual served JS source remains unverified |
| `kalman-investment-hub-us` | Latest READY Production `dpl_EjWXmvkHE6XtKdr8ko3c7ipvKqXi`, `source=cli`, alias `kalman-investment-hub-us.vercel.app` | Separate site; source file tree displayed `src/app.js,index.html,style.css`, with no API folder in that tree. Current `/api/assets` and `/api/account` runtime response NOT attested; do not assume healthy APIs |
| `kalman-investment-hub-kr` | Latest READY Production `dpl_HuDFT3yJrSjfpC63ZYDknB58ixkK`, `source=cli` | Retrieved its **actual deployed `src/vercel.json`** with a rewrite `/api/:path* -> https://kalman-investment-hub-v2.vercel.app/api/:path*` plus local `/market-pulse -> /api/market-kpis`. Thus KR API behavior **depends on the main Hub endpoint**; direct runtime reachability unverified |
| `kalman-investment-hub-v2-staging` | Latest READY `dpl_8V5GjXVpU2tEixvcNEh6hwKiY32C`; source tree includes `src/api/assets.js` and `src/api/health.js` | Appears to have an older independent CLI/staging artifact. This is **not** the candidate built in the audit CI and must not be treated as tested current release |
- Connected `list_project_routes` currently returned empty configurable project-level route arrays for main/US/KR; this does **not** negate deployment-file `vercel.json` rewrite.
- Public anonymous `/api/health` GET attempts on main/US/staging were inaccessible via available external web read path. The actual served APIs and data remain **UNVERIFIED**.
- `list_deployment_files` for main Git deployment returned `404 file_tree_not_found`; dedicated US/KR and staging CLI file trees were accessible. US `app.js` contents were truncated by connector output limits, so entire actual deployed code was not attested.

## 4. Release plan (operator approval required for each Production mutation)
1. **Provenance freeze:** archive current main/US/KR/staging deployment IDs, aliases, source roots, version and rollback candidates; independently inspect served health and JS using properly authorized web access.
2. **Choose main-source strategy:** either remove unintended research repo auto-deploy link or explicitly link the correct Kalman source with correct root/build settings. *Both are production configuration changes; neither is authorized in this audit*. CLI source deployment can coexist only with a planned automatic-deploy policy; prevent IS research commits from unintentionally replacing the website.
3. **Isolated preview or safe staging:** only after environment/SSO/alias review, deploy the pinned **30-file candidate** to an appropriate separately approved non-Production project (not using `deploy_investment_hub_v7436_ci.sh`).
4. **Live-readonly API acceptance:** validate GET-only health, the actual `/api/assets?view=control` contract, version hashes, account redaction, net_return NULL, gross return semantics, KR API rewrite, and independent US API route.
5. **Reconciliation:** independently verify actual Toss fee denomination, historical add-on order linking and per-order fees. No restoration of net performance without broker attestation.
6. **Canary/rollback:** user-approved alias promotion or swap only after 0 errors in smoke tests; preserve previous deployment for rollback; never issue a trade/order while doing web deployment.
7. **Separate Kalman engine LIVE changes:** do not conflate website deployment with `/opt/kalman/app` execution mirror source. Its runtime SHA and trade impact remain independently blocked.

**Bottom line:** Reproducible protected build PASS. The main Production website Git connection is still wrong, KR depends on main API, dedicated US API runtime is not attested, and five corrupted Neon Production net returns persist. **NO PRODUCTION RELEASE APPROVED.**
