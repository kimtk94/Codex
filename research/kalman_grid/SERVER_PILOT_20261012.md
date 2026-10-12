# V2.5 server pilot, 2026-10-12

Remote host: taehoonserver.
Research clone: /home/taehoon/kalman-grid-v25-git
Input: /home/taehoon/kalman-data/assets-1h/{QQQ,QLD}_1h_2017plus.parquet

- Server discovery tests: 12/12 passed; ledger tests: 10/10 passed.
- Full multi-year 30-scenario V2.5 sweep **not completed**: initial run exposed a 3e-32 Decimal asset precision drift; subsequent run was terminated due to computational cost of auditing all historical orders at each observation.
- Quantize purchase quantities to 12 decimal places patch committed: acc39e4661a3c389a83a87813fb69405e54efb0a.
- A **local-only 300-bars-per-symbol smoke pilot** completed 30 scenarios:
  /home/taehoon/kalman-data/grid_v25_research_pilot/sweep.csv
- QQQ pilot: Static 0.14% = +0.200%; rolling 140 bars 0.14% = -3.749%.
- QLD pilot: Static 0.14% = +0.160%; rolling 140 bars 0.14% = -6.584%.
- These samples have different calendar end dates (QQQ 2020-09-21, QLD 2020-10-02).
- Rolling 700 bars equals Static within 300-bar smoke window by construction.
- This is an hourly-CLOSE observational model: no path-dependent intrabar matching, FX, spread, tick size, slippage, market-hour, corporate-action, or real order reconciliation. These results are **not** evidence of achievable returns.
- Server pilot runner was modified locally to slice the first 300 rows; GitHub runner is NOT truncated.
- Production code/credentials untouched. Not deployed to LIVE.

## Next
1. Fix unbounded audit complexity (active-order indexing and periodic full audits).
2. Add restart/idempotence/transactional fill tests and cost/FX assumptions.
3. Execute complete date-aligned 30-case OOS sweep.
4. Prefer actual 1-minute bars and compare deterministic OHLC path sensitivities.
5. Do not approve trading before profitability and drawdown gates pass.
