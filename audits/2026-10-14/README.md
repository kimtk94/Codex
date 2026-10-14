# Kalman integrated audit - 2026-10-14

Status: READ ONLY; not production-approved. This branch must not deploy to LIVE.

## Ownership
- GitHub: source code, tests, run manifests and reproducible research procedures.
- Google Drive: reports, exported audit results, large historical data and handoff documents.
- Neon: operational database (read-only during audit).
- Vercel: deployed views; no changes without explicit approval.

## Verified observations
- Neon production branch ready, but protected=false when inspected.
- public.v_latest_dashboard_snapshot selects last READY/STALE snapshot per market without recomputing staleness.
- READY but expired at generation: CRYPTO 517/522, GLOBAL 537/539, KR 1/18, US 0/144.
- Mirror state count: OPEN=1, CLOSED=39. Broker reconciliation pending.
- Latest US pipeline success 2026-10-13T19:38:49.891Z. Historical CSV cache is not proof of live outage.
- Vercel Hub V2 production Git deployment metadata references IS_Analysis_V3. Source-mapping review required.
- Hub US latest production deploy source cli READY; deployment SHA reconciliation pending.
- Desktop Commander remote shell audit blocked by monthly usage limit.

## Workstreams
00 operations and release gates; 01 US LIVE reconciliation; 02 US strategy OOS; 03 crypto grid fill realism; 04 crypto regime risk; 05 data quality/freshness; 06 harness orchestration; 07 Vercel/Neon source mapping.

## Minimum gate
Treat pipeline status and freshness as separate fields. Do not infer FRESH from READY. Define freshness against UTC evaluation time and stale_after. Record unknown/null timestamps as UNKNOWN and contradictory timestamp ordering as INVALID. Research-only until reviewed.

## Next actions
1. Audit snapshot producer computation for CRYPTO and GLOBAL TTL.
2. Read-only server audit to compare live config, process, open orders and broker holdings.
3. Map Vercel project to approved repo and commit.
4. Adopt versioned reports under Drive/Kalman_Diagnostics; never store secrets or full sensitive trade payloads.
5. Keep changes on audit branch; require review before merging or deployment.
