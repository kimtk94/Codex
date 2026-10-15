# Kalman 34th audit — existing staging access boundary and complete candidate API surface
Observed: 2026-10-15 KST

**DECISION: 222_TESTS_PASS / 12_API_SURFACES_INSPECTED / STAGING_RELEASE_HOLD / LIVE_P1_UNFIXED**

## Operations permitted and executed
- Authenticated Vercel **GET-only** on MAIN, US, KR and STAGING project settings; no secret-value fetch, project update, deployment, or alias change.
- GitHub changes exclusively on `kimtk94/Codex@audit/kalman-control-20261014`, with 100% synthetic SQLite/PostgreSQL test data and complete local v7.4.36 30-file bundle building in GitHub Actions.
- No live brokerage operation, Production Neon DML, server writes, Vercel deployment or Production configuration mutation.

## Verified project protection, not an assumption
Connected Vercel `get_project` returned:
| Project | SSO protection | Additional inspected staging fields |
|---|---|---|
| `kalman-investment-hub-v2` (MAIN) | enabled | not a claim about all auth layers |
| `kalman-investment-hub-us` | enabled | — |
| `kalman-investment-hub-kr` | enabled | — |
| `kalman-investment-hub-v2-staging` | **disabled** | password protection disabled; 0 trusted-IP rules; 0 custom bypass entries |

`staging_runtime_api_access_verified:false`, `staging_credentials_isolated_verified:false`, `staging_database_isolation_verified:false` record missing evidence, not positive evidence of exposure. SSO disabled alone cannot certify public anonymous reachability; the actual stage API HTTP response was NOT independently accessed.

Sanitized, no-secret evidence: `audits/2026-10-15/staging_protection_snapshot.json`.

## Full candidate API static security scan
The audit branch fully rebuilds v7.4.36, opens all **12** final `api/*.js` files from the generated 30-file manifest and scans method markers, SQL write markers, environment **names only**, and sensitive route names. These are **static indicators**; their presence is not proof that routes are callable, mutative or unauthenticated.

- API files scanned: **12**; predefined sensitive paths requiring independent review: **6**.
- Five paths with static `POST|PUT|PATCH|DELETE` method markers:
  - `/api/analyze`
  - `/api/ingest/etf`
  - `/api/ingest/manual-snapshot`
  - `/api/position-ledger-tick`
  - `/api/position-ledger`
- SQL mutation regex matched **0** final API files. That is **not** evidence of read-only behavior: writes can happen through helper modules, database client functions, indirect API calls or imported code.
- The remaining `/api/position` is conservatively flagged as a manually reviewed sensitive route even if it lacks these coarse markers.
- This scanner does not execute application JavaScript, load real env variables, call API URLs, or obtain real accounts.

Audit code: `audits/2026-10-14/quality/staging_api_surface_gate.py` and `test_staging_api_surface_gate.py`.

### Preflight policy, fail closed
To even request a separate staging operator release, require **all**:
1. Confirm exact Vercel STAGING `project_id` and active alias target immediately before deployment, and capture rollback state;
2. Demonstrate active access protection (SSO or independently demonstrated password/network isolation, not an assumed hidden secret);
3. Attest that staging API keys/authorization and every privileged environment secret are **independent of LIVE trading**;
4. Attest non-Production isolated datastore with explicit read-only permissions (or harmless synthetic-only DB), no write privilege to Production Neon;
5. Verify API runtime auth/method contracts and that the six sensitive endpoints cannot perform live trading or Production writes;
6. Verify GET-only actual runtime `/api/health`, `/api/assets?view=control` and US/KR shared proxy on an approved test endpoint, and ensure no sensitive payloads are exposed;
7. Separately obtain operator approval for **staging-only** deployment and no Production alias, Git link or LIVE server change.
Even if all static flags are asserted true, the audit gate returns `can_deploy:false` — the static report is not an actuator or release authorization.

`stage_decision` for the connected STAGING snapshot returns:
```
{"verdict":"STAGING_RELEASE_HOLD","reason":"STAGING_AUTH_PROTECTION_MISSING","can_deploy":false}
```

## CI results and caveats
GitHub Actions final **COMPLETED SUCCESS**:
https://github.com/kimtk94/Codex/actions/runs/38660358343

- **207** offline unit methods PASS (including new auth, environment, mutation-marker and fail-closed cases);
- **15** disposable PostgreSQL mirror integration methods PASS;
- **222** total unittest methods PASS; 1,000 valid and 2,000 negative seeded cash-flow scenarios remain nested in two of the offline methods, not counted as independent unittest methods.
- Full v7.4.36 candidate build: 30 source files, 12 API JS, `api_net_return_masked:true`, `ui_net_evidence_guard:true`, `release_authorized:false`.
- Source fingerprint comparison still confirms currently active MAIN uploaded JS/API matches unguarded `main` v7.4.36; actual HTTP response and browser output remain unverified.
- Initial CI failed because our audit-only SQL-regex pattern for `UPDATE table_name` was too narrow; fixed the scanner, not the production application. Final CI passed.
- API scanner result lists **five HTTP write-verb markers**, no direct mutating SQL markers; do not infer that the five endpoints are exploitable without independent runtime evidence.

## Live P1 and next safe milestone
- Main Vercel active alias deployed source still unguarded based on exact file hashes and five inflated Neon historical `net_return` values remain unchanged. MAIN API is shared by US and KR sites.
- **Do not run** `deploy_investment_hub_v7436_ci.sh` as a test; it performs real production deploy/promote.
- Next priority is isolated staging access protection + synthetic/least-privileged env design, then only a separately operator-approved staging deployment, paired with explicit rollback IDs and GET-only three-site smoke. These steps were NOT executed.
- Desktop Commander usage was exhausted in the prior audit, so live server runtime SHA remains unverified; no further remote terminal call attempted here.

**Bottom line: The candidate web package and CI pass, but the existing staging target is not proven safe. Keep P1 Production and staging release on HOLD.**
