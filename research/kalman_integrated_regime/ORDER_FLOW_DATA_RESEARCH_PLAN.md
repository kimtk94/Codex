# Kalman QLD / QQQ — Trading Volume, Large Prints, Order-Flow Research Plan

**Status:** RESEARCH_ONLY · LIVE_HOLD · 2026-10-31  
**Owner:** Kalman quantitative research  
**Related work:** PR #477, 40-axis exploratory joint policy sweep  
**Scope:** U.S. equities and ETFs (QLD / QQQ), historical Alpaca SIP, optional FINRA aggregates.

## 1. Source-of-truth status: verified code vs available APIs vs confirmed access

| Layer | Observable field / unit | State | Evidence / caveats |
| --- | --- | --- | --- |
| Alpaca SIP historical 15-minute QLD/QQQ bars | OHLC, `v` / shares per 15m | **DOWNLOADER CONFIRMED**, but volume not used in current classifier | `sip_backfill.py` writes `volume`; `run.py` PRICE/EXTRA exclude volume; historical coverage must be rerun per period |
| Alpaca historical bars extra fields | `n` / trade count; `vw` / volume-weighted average price | **API DOCUMENTED**, not yet retained by backfill | `https://docs.alpaca.markets/us/reference/stockbars`; do not assume native vs adjusted prices/volumes are interchangeable |
| Alpaca historical SIP individual trades | `p`, `s`, `t`, `x`, `c`, `i`, `u`; USD print notional = `p*s` | **API DOCUMENTED; LIVE ACCOUNT ACCESS UNCONFIRMED** | `https://docs.alpaca.markets/us/reference/stocktradesingle-1`; check probe run 41188163034 |
| Alpaca historical quotes | bid/ask price and displayed size, timestamp | **API DOCUMENTED; ACCESS + DEPTH UNCONFIRMED** | `https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data`; top-of-book quotes do not reconstruct an entire depth-of-book |
| FINRA ATS / non-ATS weekly aggregate | reported shares and trades, reporting week, publication time | **PUBLIC METHODOLOGY CONFIRMED; BACKFILL NOT VERIFIED** | `https://www.finra.org/finra-data/browse-catalog/otc-transparency`; weekly and delayed, not contemporaneous intraday decision data |
| Investor identity / institutional net buying / full consolidated limit order book | none | **NOT IN SIP PRINTS** | Inferring aggressor from aligned quote is only a classification estimate, not participant identity or submitted parent orders |

**Never conflate:** a big *print* (an execution), a large *order* (possibly split across prints), a dark-pool/ATS transaction (execution venue), and institutional net flow (identified beneficial owner, unavailable).

## 2. Correct hierarchy and scope

**P0 — Volume baseline, from data already collected**

- Daily RTH shares: sum 15m `volume` for each completed NYSE session (09:30–16:00 New York time), QQQ and QLD separately.
- `rvol20`: today's completed RTH volume / median of previous 20 **completed** exchange sessions for the same instrument; baseline strictly excludes current session.
- `volume_z20`: log RTH volume compared to trailing 20 completed sessions using robust median/MAD or rolling z-score. Zero-variance cases become missing/flagged; do not invent infinite values.
- `rel_turnover`: `close * volume` is approximate bar turnover, not exact summed trade notional. Use documented price/volume adjustment basis and flag split dates.
- `qld_qqq_volume_ratio_change`: compare instrument-normalized RVOL, **not raw share counts** (share prices and shares outstanding differ).
- Optional intra-session signal: compare cumulative volume through *completed* 15m bar `k` with historical cumulative volume through the **same bar index k** and similar session type (regular/early close) in the prior 20-60 sessions; shift previous information appropriately. Never mix early-close sessions with normal sessions uncritically.

**P1 — Bar microstructure summary**

- Extend private SIP backfill to retain count `n` and `vw` when present; zero / missing / null have separate semantics.
- `mean_print_shares = v/n` only if count > 0.
- `vwap_deviation = (close/vwap)-1`; verify adjustment and accumulation basis.
- `trade_count_rvol20`, `mean_print_size_z20`; note late reporting can change historical aggregates.
- Validate that 15m aggregation matches minute sums, within tolerance and published bar semantics; identify explicit exceptions.

**P2 — Large individual SIP prints**

- First prove historical 1-minute entitlement on QQQ and QLD with the read-only probe:
  `research/kalman_integrated_regime/sip_large_trade_probe.py` and
  `.github/workflows/kalman-qld-trade-size-probe.yml` (run `41188163034`).
- Probe only old, bounded ranges; paginate to completion; return aggregate statistics (large-print counts, notional distribution, exchange / condition breakdown), **never raw SIP prints in public GitHub Actions artifacts**.
- Remove `u=canceled` / `u=incorrect` and handle `u=corrected` according to trade ID/correction semantics; dedupe by exchange + trade ID + correction history; require auditable counts.
- Filter or separately retain condition types based on documented eligibility; `c` determines how reports contribute to OHLC or volume. Off-exchange, late, odd-lot, and special-condition prints require explicit definitions.
- Print notional USD `p*s`. Provisional fixed bands: >=$100k and >=$1m; also rolling symbol-specific 99th, 99.9th percentile thresholds **fitted only on history**.
- Signals: `large_print_count_share`, `large_print_notional_share`, `large_print_rvol`, `large_print_concentration`, venue breakdown. No directional institutional-buyer claims.
- **Budget control**: one small interval first; then a single day; then one test month; only after page count, download rate, storage volume, license and entitlement checks pass scale to 2024–2026. Avoid 429 storms and API overuse.

**P3 — Quote-aligned directional estimates**

- Require a historical SIP quote entitlement and timestamp-aligned bid/ask samples. Map trade `t` to the **latest quote at or before t** without a future quote. Reject stale, crossed or locked quotes per a predefined policy.
- `aggressor_estimate`: execution at ask vs bid or midpoint; mid-quote trades are ambiguous, not automatically buys/sells. Audit late reporting and trade conditions.
- `signed_volume_estimate`, `order_flow_imbalance_estimate`, `bid_ask_spread_bps`, quote staleness; this is not true institution net flow and not full level-2 order-book depth.
- Do not claim order-level reconstruction or iceberg detection from prints alone.

**P4 — ATS / non-ATS aggregate and broader context**

- FINRA transparency reports: weekly total shares/trades by issuer/ATS with a **publication delay**, and potentially separate summary frequencies. Feature timestamp must be **publication/availability time**, not report week start.
- Use only as lagged structural feature, never same-week real-time shock signal. Test actual symbol coverage for QLD and QQQ before GO.

## 3. Dataset contracts, retention and leakage prevention

1. Store `source`, `feed`, `symbol`, `exchange_timezone`, `ts_utc`, `trade_session_date_ny`, `bar_start`, `bar_end`, `market_close_time`, `available_at_utc`, `retrieved_at_utc`, `adjustment`, `version`, `license_scope`, `input_digest` for each dataset. Trade and quote sources also need full pagination coverage markers.
2. Keep adjusted historical bars and **unadjusted trade prints** separate until a split-safe transformation is explicitly tested. Historic QLD leveraged ETF corporate actions make naïve mixing hazardous.
3. Compute features only from data available at the decision timestamp; close-of-session bar may drive a **next-session** entry, not an earlier same-session decision. For online signals use last completed bar and provider latency margin.
4. Apply exchange calendar and daylight saving time, variable early-close lengths, partial sessions, late corrections, missing bars, and symbol-market coverage tests; **missing => HOLD, never zero-filled into a qualified trading feature**.
5. Raw entitlement-restricted SIP tape stays private; GitHub public artifacts contain aggregate QA tables, reproducible hashes and no API credentials/raw prints.
6. Verify provider terms for licensed SIP replay, caching and redistribution before persistent backups.
7. Distinguish the **trade size** from Kalman's **own position size**: print-notional thresholds do not determine allocation without independent position-risk validation.

## 4. Controlled model increments

| Arm | Features | Purpose |
| --- | --- | --- |
| A | Current price-only model | Baseline |
| B | A + P0 volume | Incremental value of relative volume |
| C | B + P1 trade count / VWAP | Bar-level microstructure increment |
| D | C + P2 large-print concentration | Separate large-print value |
| E | D + P3 quote-aligned signed flow | Optional directional inference |
| F | E + P4 published weekly ATS features | Optional lagged structural context |

Use **identical eligible timestamps**, training/validation splits, execution policy, investment allocation and fee/slippage assumptions for each pair. Report both **policy unchanged** and **re-optimized policy** separately; changing classifier and policy jointly confounds feature attribution.

Outcomes per arm: annual return, worst-year return, drawdown, trade count, win rate, trade turnover, transaction cost, coverage, calibration, and regime/year stratification. Compare 2025 & 2026 as **exploratory previously-referenced periods**, not fresh untouched validation for a newly selected feature combination.

The existing joint-policy goal of >=500 policies with **>=15 completed trades in each of 2025 and 2026** is a *coverage criterion*, not a statistical guarantee or profitability target. Do not enforce it by cherry-picking profitable outcomes or silently weakening trade-count conditions. Any new model features change the candidate universe and require a separately versioned study.

## 5. Evidence gates

- **P0 GO** when existing 15m volume completeness matches RTH session checks; split/corporate-action basis is documented; lag/no-lookahead unit tests pass; model A vs B reproducible.
- **P1 GO** after provider `n`/`vw` payload presence and cross-granularity reconciliation checks; otherwise HOLD.
- **P2 GO** after probe confirms entitlement, full pagination, non-zero prints on QLD and QQQ, correction/condition policy, bounded cost and rights to use. A workflow queued/passed lint is **not** data-access confirmation.
- **P3 GO** only with quote entitlement, synchronized time and valid trade-direction classification audit. Otherwise HOLD.
- **P4 GO** after symbol coverage, report release dates and lagged join verification. Otherwise HOLD.
- **LIVE always HOLD** pending separate untouched forward validation; no merge of experimental signals into execution.

## 6. Project links / reproducibility

- Experimental PR: https://github.com/kimtk94/Codex/pull/477
- Volume captured but unused: `research/kalman_integrated_regime/sip_backfill.py` → `run.py`
- Initial individual SIP print probe: https://github.com/kimtk94/Codex/actions/runs/41188163034
- Structured 10k study (separate): https://github.com/kimtk94/Codex/actions/runs/41185397422
- Official trade schema: https://docs.alpaca.markets/us/reference/stocktradesingle-1
- Official bars schema: https://docs.alpaca.markets/us/reference/stockbars
- FINRA transparency publication information: https://www.finra.org/finra-data/browse-catalog/otc-transparency

**The plan distinguishes documentation-supported capability from *verified entitlement / actual collected observations*. No P2 experimental signal is production-ready.**
