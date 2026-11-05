# Kalman — Cross-Symbol US Stock/ETF Volume & Aggressor Research Contract

**Date:** 2026-10-31  
**Branch/PR:** `research/qld-integrated-regime-20261031` / #477  
**Scope:** U.S. listed stocks and ETFs only; licensed historical Alpaca SIP. **RESEARCH ONLY / LIVE HOLD**.

## Why this contract exists

QLD/QQQ established (i) complete-session 15-minute SIP volume, RVOL20 and volume z-score, (ii) an exploratory ten-second historical trade/quote matching proof, (iii) a negative 2026 incremental model-performance result even when 2025 improved. Those results **do not automatically transfer to other symbols**. They justify reusable *data/analysis methods*, not deploying the same signal coefficients or trade thresholds.

## Universe: source of truth, not hardcoded unlimited web scraping

Read the versioned project manifest `kalman-toss-gateway/config/market-data-v2-universe.json`; select only `market == 'US'`, `kind == 'equity'|'etf'`, `provider == 'yfinance'` and valid U.S. symbol strings. QLD is included as a specific pre-existing research exception because it is used in `sip_backfill.py`.

Examples confirmed in that configuration:

| Class | Examples | Application |
| --- | --- | --- |
| Broad / sector ETFs | SPY, QQQ, IWM, DIA, SOXX, SMH | Same methodology; reference volume/time-of-day statistics by symbol |
| Individual equities | MU, IONQ, COIN, MSTR | Same methodology; handle earnings, liquidity, splits, episodic large prints |
| BTC-linked ETFs | IBIT, FBTC | US SIP method applies to ETF **shares**, not directly to the BTC blockchain or spot exchange |
| Credit / bond / gold ETFs | HYG, LQD, TLT, GLD | Historical SIP price/size method applies, return behavior and macro controls differ |
| Leveraged ETF | QLD (explicit exception) | Corporate-action adjustments and split-safe volume definitions essential |

**Out of this adapter:** `BTC-USD` and Upbit assets require cryptocurrency trade-book exchange APIs; KRX/KOSDAQ equities require Korean venue/trade data; foreign indexes, VIX, TNX, FX are not executable SIP equity/ETF quotes. These families require independent adapters and approved data rights.

## What is reusable across symbols

1. **Past 15m OHLCV quality:** XNYS exchange calendar, regular-session expected bar timestamps, exact no-duplicate checks, no artificial filling of missing 15-minute bars, source adjustment basis and availability time.
2. **Relative volume:** `RTH_daily_shares`, `RVOL20 = current completed regular-session shares / median(previous 20 complete US sessions' shares)`, symbol-specific `z20`, `>=2x` flag. Never compare raw SPY shares directly with MU or QLD shares. A partial or missing previous day *invalidates* later 20-session baseline rather than being silently skipped.
3. **Big prints:** raw trade notional `price * shares` for provisional >=$100k and >=$1m bands; a rolling symbol-percentile rule should be fit on history preceding each decision date and tested alongside market-wide absolute bands. Venue/condition/correction filtering is not validated in the initial sample.
4. **Buy-/sell-initiated estimates:** match to a **strictly earlier** valid best-bid/ask quote; buy at ask, sell at bid, inside-spread low-confidence, midpoint/late/outside/stale UNKNOWN. Report share sums and unknown coverage. **Every trade has a buyer and seller; this is aggressive side estimation, not institutional net flow.** Do not compare net pressure when large unknown coverage exists.
5. **Volume/flow regime buckets:** low/normal/high RVOL, high/low VWAP deviation, high/low large-print concentration and high/low signed pressure *estimated*; calibrate cutoffs using symbol-specific past history only, never use outcomes to define the universe.
6. **Model audit:** identical common historical days and fixed execution per symbol for A price only, B price+volume, C price+macro, D price+macro+volume. More refined quote/order-flow arms only when historical sample, correction audit, quote coverage and leakage tests pass.

## Implementation + safe pilot

- `research/kalman_integrated_regime/us_multisymbol_microstructure.py`
  - `approved_us_symbols()` reads the current repo US equity/ETF manifest.
  - `select_symbols()` enforces an allowlist and unique maximum five symbols per research probe.
  - `symbol_volume_features()` generalizes daily 15min RVOL without mixing symbols.
  - `--mode volume --input-bars private.parquet` computes derived daily features with zero LIVE writes and *requires previously retrieved private bars for the exact symbols*; it is not itself a multi-year downloader.
  - `--mode probe --symbols SPY,IWM,SMH,MU,COIN` performs an *actual 10-second* historical Alpaca SIP trade+quote sample. One minute of QLD/QQQ feasibility is already validated in previous tests. It only publishes aggregates; raw individual print/quote data is not persisted in public artifacts.
- `research/kalman_integrated_regime/test_us_multisymbol_microstructure.py`: universe isolation, no non-US/crypto/index, instrument-specific RVOL, missing bar segregation and duplicates.
- `.github/workflows/kalman-us-multisymbol-microstructure.yml`: no-SIP synthetic tests first; then 5-symbol read-only bounded source access; linked run https://github.com/kimtk94/Codex/actions/runs/41191170517. Status must be confirmed separately rather than assumed.

**This is a _pilot_**, NOT evidence that Alpaca is already providing years of SPY/MU/IONQ/etc trade and quote history, and not evidence that any new model has predictive power.

## Rollout gates

| Gate | PASS condition | Failure status |
| --- | --- | --- |
| 0 Allowlist | Valid symbol and US equity/ETF; approved provider; calendar rules | HOLD_UNSUPPORTED_MARKET |
| 1 Source access | Historical SIP quote+trade API and full pagination for short predeclared window; quota + terms | HOLD_ACCESS |
| 2 Integrity | Complete bar sessions; provenance, adjustment and splits; trade/quote time; corrections + conditions; sum reconciliation | HOLD_DATA |
| 3 Classification | Predefined minimum classified high-confidence share fraction tested across symbols, weeks, earnings/outlier dates; unknowns retained | HOLD_CLASSIFICATION |
| 4 Predictive value | Same timestamp cohorts, fixed trade cost and execution, purged expanding/nested forward validation, calibration + 2025/2026 year/regime effects | HOLD_MODEL |
| 5 Promotion | Independent *untouched* forward OOS + portfolio constraints + user-authorized live change | LIVE_HOLD |

Do **not** blindly copy QLD volume model into other symbols. QLD four-arm result showed volume improved 2025 but worsened 2026 outcomes, in spite of correct data access. Use individual symbol & sector/asset cross-sectional baselines before any shared representation or hierarchical feature selection. Pilot stock universe is not the same as account holdings or an approved trade list, and no production position or risk allocation changes are authorized.

## Further recommended research

- Multi-year 15m SIP OHLCV backfill for exactly the approved target symbols with monthly pagination and private data storage; preserve older original data and avoid publishing licensed prints.
- Test print-correction identifiers, late report conditions, event-time vs publish-time ingestion, quote timestamp skew and unknown fraction by liquidity decile.
- Year- and regime-stratified volume model ablations; comparison within common months 2025 vs 2026; separate training-only feature selection and untouched future validation.
- One report per symbol with data coverage, RVOL quantiles, classified buy/sell/UNKNOWN shares, high-value print ratios, cost/return/MDD/AUC, verdict.


## First five-symbol full-history SIP dataset gate: PASS (2026-10-31)

[GitHub Actions 41198243032](https://github.com/kimtk94/Codex/actions/runs/41198243032) succeeded after restoring a sufficiently large bounded per-month page allowance; [private aggregate report on Drive](https://drive.google.com/file/d/1y0Srq9mnVNabeFl59A9jnkNgSigotBO-/view?usp=drivesdk).

- Source: Alpaca SIP `adjustment=all`, `15Min`, 2024-01-01 through 2026-10-30, 34 calendar months, **272 paginated requests**.
- Rows returned: **221,014** historical 15-minute bars across **SPY, IWM, SMH, MU, COIN**.
- Complete RTH sessions: **711 for each symbol; 3,555 / 3,555 symbol-sessions**. Missing/partial RTH: **zero**.
- Bar trade count (`n`) and bar VWAP (`vw`) were populated in **all observed returned bar rows** for all 5 symbols. These fields support further study, but prints/signed flow still need condition/correction audits.
- The raw licensed SIP bars were held on an ephemeral Actions runner and deleted; only derived QA figures entered the artifact.

| US ticker | 2025 median daily shares | 2026 YTD median daily shares | 2025 RVOL20 >=2x day fraction | 2026 YTD RVOL20 >=2x day fraction |
| --- | ---: | ---: | ---: | ---: |
| SPY | 57,812,312 | 42,768,296 | 4.40% | 0.48% |
| IWM | 28,994,488 | 23,954,425 | 4.80% | 0.00% |
| SMH | 6,948,826 | 7,554,525 | 6.00% | 7.18% |
| MU | 17,286,245 | 31,121,178 | 6.40% | 2.39% |
| COIN | 7,713,512 | 7,394,361 | 9.20% | 5.74% |

**Interpretation:** the distributions and scales differ materially by ticker. A common *algorithm* is feasible; a common raw-share threshold is not. 2026 is only through October, so direct full-year seasonality comparisons remain provisional; compare matched Jan–Oct for validation.

**Model gate:** historical data access & completeness GO. Do not call model predictive or return improvement GO until paired same-date evaluation per ticker. Data-ready is not live-ready.

### Next-stage cross-ticker prediction screen

`us_multisymbol_volume_screen.py` defines paired price-only (3 features) vs price+volume (5 features), with identical lagged training / 2025 and 2026 test signal dates. Tests separate *next-session open-to-close direction* and *next-session large absolute move* (threshold learned on training labels only) using AUC/Brier/log loss. Both require a separate source-run result and cannot be presented as a trading backtest. Workflow `.github/workflows/kalman-us-multisymbol-bars.yml` runs the screen while private bars are present and publishes only a derived JSON.
