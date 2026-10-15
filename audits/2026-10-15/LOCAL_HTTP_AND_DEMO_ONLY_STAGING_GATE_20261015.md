# Kalman 35th audit — synthetic-only live-handler HTTP replay and safe Staging alternative

**Date:** 2026-10-15 KST  
**Release status:** `230_TESTS_PASS / DEMO_ONLY_BUNDLE_BUILD_PASS / STAGING_RELEASE_HOLD / P1_PRODUCTION_HOLD`

## Boundary
- Authenticated GitHub updates only to `kimtk94/Codex@audit/kalman-control-20261014`.
- GitHub Actions ephemeral runner + ephemeral disposable Postgres 16/SQLite. The 17 HTTP cases bind **127.0.0.1 only**, with synthetic in-memory stubs. There is no connection to Vercel, Neon Production, actual broker API, remote Kalman server, third-party FX service, or credentials.
- No staging deployment or public URL generated. No Vercel settings/aliases/Git link changes; no Production DML, live orders, server edits or main branch merge.
- This report uses sandbox/mock terms precisely; do **not** claim live HTTP smoke or actual SSO enforcement from the loopback cases.

## A. Actual protected bundle handler execution via local HTTP (NEW)
`quality/staging_local_http_smoke.js` loads the actual rebuilt v7.4.36 API JavaScript source modules from its 30-file manifest (NOT extracted source snippets), then executes them inside Node VM with a **blank process.env**, strict allowlisted dummy `require` stubs, a blocked `fetch`, and a 127.0.0.1-only HTTP server.

Six real source handlers are exercised: `/api/health`, `/api/assets`, `/api/ingest/etf`, `/api/ingest/manual-snapshot`, `/api/position-ledger-tick`, `/api/position-ledger`. 17 fixed request cases cover GET/POST failures and fake success, including US/KR *simulated* main API routing:
- `GET /api/health` 200 and reports trading/account execution disabled; `POST` 405.
- `GET /api/assets?view=control` 503 `DB_NOT_CONFIGURED` and account view 503 `ACCOUNT_GATEWAY_NOT_CONFIGURED` with no DB/gateway.
- `POST /api/assets?view=control` 405.
- Unauthorized `POST /api/ingest/etf` and `POST /api/ingest/manual-snapshot` 401; GET ETF ingest 405.
- Unauthorized `GET/POST /api/position-ledger-tick` and `POST /api/position-ledger` 401.
- **Important privacy boundary:** `GET /api/position-ledger` returns **synthetic** ledger records even without a token check within this handler; `GET /api/ingest/manual-snapshot` returns synthetic cache metadata with no token check. These routes may be intentionally publicly readable behind Vercel SSO but require explicit staging protection because original existing staging has SSO and password protection disabled.
- Simulated US/KR rewrites to the main synthetic API returned identical expected statuses, **not** a real HTTP test of Vercel's proxy or aliases.
- Stubbed source operations produced **0 outbound fetch calls and 0 attempted writes** for these selected inputs. That does not prove absence of other methods/paths that could write in a credentialed runtime.
- Synthetic ledger identifiers and fake payloads never come from actual accounts.

## B. Reproducible protected DEMO ONLY staging source profile (NEW)
`quality/build_demo_only_staging.py` takes the already protected audit-branch v7.4.36 30-file bundle and generates an **offline-only** completely synthetic variant:
- Retains exact 30 known filenames.
- Replaces 11 backend API modules with explicit `GET -> 503 STAGING_DEMO_ONLY_NO_BACKEND`, `non-GET -> 405`. Replaces health with safe GET 200 `SYNTHETIC_DEMO_ONLY_NO_REAL_TRADES` and `trade_enabled:false`, `account_trade_execution:false`.
- Inerts all **10** helper JavaScript libraries by replacing them with empty module exports, and replaces **3** static JSON data files with demo markers and absent live values.
- Prepends a browser fetch filter permitting **same-origin /api** calls only, rejecting cross-origin fetch (including the source code's public FX API requests), backed by a `connect-src 'self'` CSP.
- Injects a prominent visible `SYNTHETIC DEMO ONLY — LIVE DATA DISABLED — DO NOT TRADE` banner and adds noindex/no-store headers, disallows cross-origin rewrites.
- Writes only a **content digest and boolean build report** to the CI audit artifact. It does NOT upload full source as a deployable artifact nor connect to Vercel.
- A production-like UI with no live APIs may display missing/unavailable sections; this is intentional. No claim of usability or browser E2E visual acceptance.
- `quality/test_demo_only_staging.py` has 8 additional tests, including Node execution of the actual synthetic API handlers and rejecting external browser fetch requests.
- Final SHA-256 digest of synthetic output bytes: `07b2db8dfd89b6166144e945cdadca4f306a8d16a2be515128508c649442c060`. A digest is not a deployment or runtime checksum.

## C. Existing Staging remains blocked
Read-only Vercel project inspection from 34th audit established `kalman-investment-hub-v2-staging` is not currently SSO/password protected; credentials/datastore isolation and live public access outcomes have not been attested.
- Normal protected full Hub candidate is **NOT approved for existing staging**: its generated APIs retain token-guarded write routes and unauthenticated-in-handler GET views, and the staging's isolation controls are unverified.
- The demo-only source is a **distinct hypothetical safe preview candidate**, not a declaration that the existing unprotected project is approved to receive it. Any deployment requires independently validated settings, alias freeze, least-privilege env, smoke plan and explicit operator approval.
- Never run `deploy_investment_hub_v7436_ci.sh` for a test; it deploys/promotes Production.

## D. CI
**GitHub Actions run 38700296186 — COMPLETED SUCCESS**:
https://github.com/kimtk94/Codex/actions/runs/38700296186

Verified job logs:
- **207** ordinary offline unittest methods PASS (includes 1,000 seeded correct PnL and 2,000 corrupt-case evaluations nested in two methods).
- **15** disposable PostgreSQL real mirror integration test methods PASS.
- **17** local HTTP request scenarios on six actual rebuilt API modules PASS (separate from unittest count).
- **8** demo-only staging tests PASS.
- **230 total unittest methods** (207+15+8). The 17 HTTP scenarios are additional executed checks, **not 17 extra unittest methods**.
- Full original protected candidate v7.4.36 build: 30 files, 12 APIs, UI masked and API net_return NULL, `release_authorized:false`.
- Demo-only source audit: 30 files, 11 backend handlers disabled, 1 fake health handler, 10 stubbed libraries, 3 synthetic data files, external fetch restricted; `DEMO_ONLY_SOURCE_VERIFIED_NOT_DEPLOYED`.

## E. Live P1 blockers unchanged
- Five historically wrong multi-entry net returns in Neon Production remain. The main active Vercel uploaded source matches the old unguarded v7.4.36 release by five independent SHA-1 source content digests.
- Live actual /api/* response and browser content remain unverified because protected Vercel endpoints were inaccessible to public reader.
- Both US and KR real deployed vercel.json source rewrites `/api/:path*` to main origin. Their dependencies are mapped, not remotely smoke tested here.
- Desktop Commander was over monthly usage; LIVE server runtime SHA not verified.

**Conclusion: Local HTTP integration + safe synthetic-only staging design PASS; neither Staging nor Production release authorized.**
