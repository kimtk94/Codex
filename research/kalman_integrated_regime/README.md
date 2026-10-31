# QLD 통합 Regime 실험 — read-only

## Fixed contract (2026-10-31)

- Asset: QLD. Signal is formed after the U.S. cash-market close; entry is the next NYSE regular-session first 15-minute candle's open at 09:30 New York time. Exclude missing first candles rather than invent fills.
- Exits: fixed TP +3%, SL -3%, final close on trading session 4 (entry session is session 1); buy and sell each 10 bp.
- Both barrier prices crossed inside one 15m candle: assume SL first; opening gap beyond barrier exits at actual open. A true ordering cannot be known from OHLC.
- One position maximum, all candidate signals versus both models evaluated over identical eligible dates. No overlapping leverage; trade-level returns compound sequentially.
- Outer test: 2025 and 2026 calendar years separately, expanding training (2024 -> 2025; 2024-2025 -> 2026), purge any training label exiting on or after the test start.
- Price-only and integrated use the same common input, feature complete-case rows, labeling, fees, execution and threshold (0.50).
- Market features only from VIX, HYG/LQD, TNX, SPY and SMH, each strictly one session lagged. Price-only can use current signal day's completed QQQ and QLD close. No USD/KRW, no FRED or latest-revised series.
- OHLC uses QLD_15m_raw.parquet in the private Drive source. Verify its regular-session completeness and date range; incomplete sessions make their 4-day windows unusable.
- All yearly rows include first/last actual signal dates, and PARTIAL if calendar 2026 incomplete. Do not infer full-year performance from partial data.

## Research data IDs

- Private QLD 15m: 1DyggclzDQ91Eew-QifEffSDGOVl7VOaq (read-shared private research copy; original remains private)
- Daily QLD/QQQ aligned CSV: 1AHPws_x_q_TALFlZUoeSSTM3ChYaSa6R (read-shared private research copy; original remains private)
- Research-only market bundle ZIP: 1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd (Drive)

GitHub Actions offline tests run on PR; actual historical experiment runs on isolated research-branch push and manual workflow_dispatch. The isolated branch trigger can be removed after acceptance. Only summary.json is uploaded as a GitHub artifact; private trade-level events are retained only within the CI runner. Do not add Drive credentials or raw data to the repository.

## Limitations and acceptance checks

- 15m OHLC does not establish within-candle TP/SL order or quote/slippage at the open. IEX-labeled or otherwise limited-venue source must not be represented as SIP market-wide execution.
- The existing daily aligned CSV ends 2026-09-04; the newer market bundle does not extend that QLD input. Report actual 2026 overlap, not a full year.
- Fixed classifier and fixed 0.50 threshold are first-stage controls; no hyperparameter selection is performed on 2025/2026 test labels.
- Features from market provider are session-dated, not independently PIT-vetted; the one-session delay reduces publication timing leakage, but does not prove point-in-time correctness of any upstream revised close.
- Equity mark-to-market MDD uses completed 15m session close, not intraday tick-to-tick worst excursion.
- GO requires no unauthorized LIVE changes, tests passing, contiguous valid bar coverage, both 2025 and 2026 with sufficient OOS samples, and benchmark results disaggregated by year. If any gate fails, status is HOLD, not a positive backtest.
