# Kalman 33rd audit — active Vercel JS/API source fingerprint proves unguarded P1 code

Recorded: 2026-10-15 KST. **Production changes: NONE**. Audited through authenticated Vercel GET-only metadata/file-UID queries plus GitHub Actions offline historical rebuild.

## 1. Key verified finding
The **actual user-facing** alias `kalman-investment-hub-v2.vercel.app` resolves to CLI deployment `dpl_BJDfGryiDg2Z5AdQvVYNG9GqeV8L`, NOT the more recent Git READY deployment sourced from research repo `IS_Analysis_V3`.

Vercel GET-only `list_deployment_files` returned these SRC files with 40-hex file UIDs. As an independent method check, the exact bytes of the complete live `src/vercel.json` were retrieved and independently SHA-1 hashed; the result matched the Vercel file UID exactly. The digest comparison below concerns these **uploaded source bytes**, not direct HTTP response bodies.

## 2. Exact fingerprint proof
Created sanitized snapshot `audits/2026-10-15/vercel_active_file_digests.json` with no tokens, cookies, account data or API responses.

Built the full historical v7.4.23...v7.4.36 website chain from read-only **pinned** GitHub `kimtk94/Codex` pre-patch `main@60dcbef3afc342ffa2156a2f650eda968df1f177` in a second isolated CI checkout. Separately rebuilt the patched audit branch's v7.4.36 in a different directory. Compared SHA-1 of generated files to authenticated active Vercel file UIDs.

**All five** independent active uploaded MAIN source file UIDs exactly match the pre-patch `main` **v7.4.36** generated release:

| User-facing MAIN uploaded source path | Actual deployment SHA-1/Vercel UID | Pre-patch main v7.4.36 | Protected audit v7.4.36 |
|---|---|---|---|
| `src/app.js` | `499cca92b14df9a35dae41f766ef6865eb111ffc` | EXACT MATCH | DIFFERENT |
| `src/api/assets.js` | `4ac771b009e8e36555f13819272a72a9ff06d14f` | EXACT MATCH | DIFFERENT |
| `src/api/health.js` | `440892bae71b46381030746ab121338bf1dc43bb` | EXACT MATCH | MATCH |
| `src/index.html` | `f1c237f2eeb6751f7b8028a7572f669c8b344855` | EXACT MATCH | MATCH |
| `src/vercel.json` | `9723f05d2db2db77e41caa039c5ee9aa209a700a` | EXACT MATCH | MATCH |

The pinned baseline builder outputs for earlier releases did NOT simultaneously match app and assets. CI output: `baseline_app_api_exact_versions: ["v7.4.36"]`, all five `matched_files` in best baseline record.

## 3. Concrete P1 code risk in matched source
Independently examined the source-identified pre-patch `main` v7.4.36 output:
- `app.js` contains `var gross=n(x.realized_return_pct),net=n(x.net_return)` and **does not** contain the audit-branch `verifiedNet(x)` guard.
- `api/assets.js` contains the direct `realized_return_pct,net_return,round_trip_cost_bps` projection rather than `NULL::numeric AS net_return` plus `NULL::numeric AS round_trip_cost_bps`.
- Therefore the **actual uploaded files behind MAIN alias are source-identical to code that lacks P1 net-return safeguards**. This is stronger than older hypothetical/historical builder-only claims.
- A distinct preceding read-only Neon audit proved **five** multi-entry positions with gross returns about -2.7% to +0.03% but falsely reported net returns approximately +90% to +199%, due to first-entry notional vs total-exit notional and missing add-on fill/fee coverage.
- Those original Production Neon metadata values were NOT updated. Thus there is a **credible active-endpoint exposure path**: production view returns invalid numbers, and uploaded API/UI source has no protective guard.
- **Do not assert we saw an actual browser screen display +198.7%**: direct anonymous HTTP GET for `/api/health` and `/api/assets?view=control` was inaccessible to available external web reader, so exact live HTTP JSON, authentication path, lambda runtime image and browser display remain UNVERIFIED.
- `get_runtime_errors` for MAIN, US and KR (last 24h) returned no grouped errors; **absence of recorded runtime errors is not functional correctness or response verification**.

## 4. Blast radius
Read-only authenticated Vercel retrieval of the actual deployed `src/vercel.json` for BOTH
`kalman-investment-hub-us.vercel.app` and
`kalman-investment-hub-kr.vercel.app` confirms:
`/api/:path* -> https://kalman-investment-hub-v2.vercel.app/api/:path*`.

The potential exposure therefore extends to the **common API serving MAIN+US+KR**. Separate client pages can differ, so do not assert each client actually renders affected net metrics without separate HTTP/browser tests.

The current Vercel project Git link incorrectly points to `kimtk94/IS_Analysis_V3`. This is an auto-deployment source-risk **separate** from the actual active CLI alias. Do not repair Git link or deploy without operator approval.

## 5. Audit-only protections and checks
- `hub_offline_release_gate.py` generates a candidate v7.4.36 30-file build with API SELECTs returning typed NULL for unverified net and cost; UI cell becomes `검증 전`. Gross price-only returns remain. No actual application deployed.
- New `active_bundle_fingerprint_audit.py` rebuilds/compares 13 historical pre-patch manifests, identifies exactly matching uploaded source, labels source-level P1 risk and flags `runtime_http_attested:false`, `release_authorized:false`. It never connects to Vercel or production APIs.
- `test_active_bundle_fingerprint_audit.py` checks byte hash matching, protective differences, unknown/invalid digests, provenance and nonauthorization.
- Baseline Git checkout in CI pinned to immutable `main@60dcbef3afc342ffa2156a2f650eda968df1f177`. The audit candidate runs separately.
- Vercel GET-only four-domain alias state was unchanged from 32nd audit.

## 6. Immediate release controls (NOT executed)
1. **P1 release HOLD** on existing user-facing web source; do NOT treat real net returns as reliable and do NOT promote linked research-code deployment.
2. Obtain authenticated **GET-only**, redacted runtime responses for MAIN /api/health and /api/assets?view=control plus US/KR API proxy, while ensuring no cookie/token or personal holdings are printed.
3. Obtain operator approval for a **staging-only** protected 30-file candidate deployment; smoke test rendered HTML and both API surfaces. Existing `deploy_investment_hub_v7436_ci.sh` must NOT be used as a dry run (contains `vercel deploy --prod --skip-domain` and `vercel promote`).
4. Agree on an alias cutover and explicit rollback of MAIN as well as US/KR downstream API acceptance. Re-query aliases just before and after any future approved change.
5. Restore 5 historical P1 fields only with independent broker-order/fees/currency provenance, not inferred ticker/time. Keep production trading engine/runtime SSH SHA a separate release gate.
6. No live orders, Neon DML, Vercel mutations, server code edits, or GitHub main merge in this audit.

**Verdict: PROVEN ACTIVE UNGUARDED WEB SOURCE / LIVE RESPONSE UNATTESTED / P1 PRODUCTION RELEASE HOLD.**
