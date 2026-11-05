# Market universe discovery evidence — 2026-10-26 KST

- GitHub Actions run: https://github.com/kimtk94/Codex/actions/runs/40210546722 (SUCCESS).
- Artifact: `kalman-research-universe-discovery`, ID 12606015380; `discovered_universe.csv`, `discovery_summary.json`.
- Runtime discovery: 2026-10-25T16:12:16.288661+00:00.
- US S&P 100 snapshot: 101 symbols, snapshot timestamp 2026-09-01T00:12:11.821515+00:00; this is **not a historical PIT index membership series**.
- Upbit current KRW markets: 299 symbols, fetched from public `/v1/market/all?is_details=true`.
- Combined **current/snapshot symbol discovery count: 400**. Minimum 200 discovery count met.
- Original target **150 US + 100 crypto NOT met** (US shortfall 49).
- **Historical OHLCV, survivorship, delisted-market history, volume and slippage quality NOT VERIFIED; research_ready=false.**
- No private API secrets, broker accounts, orders, trading systems or LIVE policies accessed.

Next: expand US 101 to 150+ from a timestamped, attributable universe; assess crypto history and delisted pairs over last three years; obtain and validate each symbol's continuous 15m/1h OHLCV and publication/adjustment policy, then construct fold-by-fold point-in-time eligibility lists.
