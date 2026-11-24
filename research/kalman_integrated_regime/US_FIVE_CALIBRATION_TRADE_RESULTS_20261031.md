# Kalman Cross-Ticker P0 Volume — Model Calibration and Historical Trading Ledger (2026-10-31)

**Research only • PR #477 • LIVE HOLD**. Five symbols: SPY, IWM, SMH, MU, COIN.

## Verified execution and immutable evidence

- P0 initial price-only versus volume prediction screen: [Actions 41198775759](https://github.com/kimtk94/Codex/actions/runs/41198775759).
- Jan–October aligned 5-session paired bootstrap and naive-prevalence baseline: [Actions 41201893245](https://github.com/kimtk94/Codex/actions/runs/41201893245).
- Four-arm probability calibration (balanced vs unweighted) **PASS**: [Actions 41206246243](https://github.com/kimtk94/Codex/actions/runs/41206246243), [Google Drive aggregate archive](https://drive.google.com/file/d/1ZvaDTywAR62_eSRIJ25X-jyZk2A1GI5j/view?usp=drivesdk).
- No-LIVE daily trading simulation with 0.30% roundtrip friction **PASS**: [Actions 41206884071](https://github.com/kimtk94/Codex/actions/runs/41206884071), [Google Drive aggregate archive](https://drive.google.com/file/d/1VNp3yV7qdCH-ElZY2a3ClrBdVbtw36hO/view?usp=drivesdk).
- Both verified source jobs had 711 complete NYSE regular sessions per ticker with zero missing/partial RTH days. Adjusted Alpaca SIP 15-minute data; private raw files were ephemeral.

## Experiment contracts

2025 and 2026 each use **January–October outcome dates**, 208 eligible signal days per ticker/year. 2025 train 231 historical eligible days, 2026 train 481. Signal after RTH close; next RTH session enters at observed opening price; no shorts, no overnight positions. Fixed direction probability threshold 0.5 (not tuned on test labels). Same price-only 3 predictors versus 5 predictors (+RVOL20, prior-20-session volume zscore). Matched cohort and prior-label exit purge. Class-unweighted and class-balanced logistic regressions both examined, but neither is approved live.

**Trading ledger assumptions:** each independent ticker account allocates 100% of notional on selected days, cash on nonentry days; equity compounded daily; fee 10bps each side, assumed extra slippage 5bps each side, **30bps roundtrip**. Daily equity-close MDD (not within-bar MDD) and completed trade win rate. Same-session exits: (1) observed end-of-day close; (2) +3% TP/−3% SL within 15-minute OHLC, stop-first if both touch same bar, worse opening price if future bar gaps through stop. These are **one-session policies**, **NOT** the older QLD 4-session holding policy. No portfolio cross-ticker correlation or combined allocation test.

## Key calibration finding

The old `class_weight='balanced'` classifier generated poorly calibrated probabilities on the *next-session large absolute move* target. Removing weights reduced Brier materially versus the balanced version:

| Symbol and year | Balanced price+volume Brier | Unweighted price+volume Brier | Train prevalence constant Brier |
|---|---:|---:|---:|
| IWM 2025 | 0.24206 | **0.20080** | 0.20665 |
| IWM 2026 | 0.23155 | **0.16256** | 0.16361 |
| SPY 2025 | 0.22133 | **0.19929** | 0.24255 |
| SPY 2026 | 0.22225 | **0.15569** | 0.16839 |
| MU 2026 | 0.30359 | **0.25107** | 0.26156 |

**Unweighted volume incremental effect remains mixed:** IWM 2025 volume versus unweighted price Brier −0.01637, 5d-block nominal CI [−0.04181,−0.00254]. IWM 2026 effect +0.00022, CI [−0.00320,+0.00324]. SPY direction+volume has adverse 2025 Brier change about +0.01329, nominal block CI [+0.00860,+0.01899]. These comparisons are numerous, uncorrected and post hoc on repeatedly consulted years; nothing can be promoted live.

## Fixed-cost historical same-session open→close results

All columns below are **unweighted** classifier, 100% capital invested on signal days, **30bps roundtrip friction**, no overnight. Positive figures are exploratory only.

| Ticker | 2025 price-only | 2025 price+volume | 2026 price-only | 2026 price+volume |
|---|---:|---:|---:|---:|
| SPY | -28.21% | -29.43% | -36.71% | -33.34% |
| IWM | -10.26% | -2.73% | -1.63% | -5.50% |
| SMH | -18.47% | -33.80% | -46.51% | -37.64% |
| MU | -15.54% | -18.77% | -16.69% | -23.50% |
| COIN | -16.95% | -12.47% | +0.76% | **+40.47%** |

**Caution: COIN historical 2026 is a one-year exception**, 46 trading days, win rate 56.52%, daily-close MDD −11.46%. COIN 2025 price+volume loses **−12.47%**, daily-close MDD **−33.77%** on 80 trades. A different 2026 class-balanced model loses **−17.32%**, showing model specification sensitivity. No strategy is defensible from one high return year where feature configurations and research hypotheses were already examined on the same history.

### Fixed intraday barrier +3%/−3% comparison

Unweighted price+volume with one-session TP3/SL3, 30bps friction:

| Ticker | 2025 result | 2026 result | 2026 daily-close MDD |
|---|---:|---:|---:|
| SPY | −33.58% | −33.34% | −33.34% |
| IWM | −9.54% | −7.25% | −10.73% |
| SMH | −31.04% | −36.37% | −38.93% |
| MU | −23.32% | −31.17% | −40.61% |
| COIN | −36.37% | **+15.43%** | −9.58% |

This one-session barrier case does not reproduce the pre-existing QLD +3/-3 max four-session policy and should not be compared to that report as an identical strategy.

## GO/HOLD/STOP

- **Data access:** GO. 5 tickers x 711 complete SIP RTH sessions. VWAP and bar trade-count present in all observed 15m source records.
- **Absolute risk probability calibration:** exploratory GO for research in unweighted logistic; **no volume feature uniformly positive** versus price only.
- **Long-only next-session return:** **HOLD all tickers**: loss in nearly all year/ticker/exit combinations; isolated COIN 2026 positive but 2025 negative.
- **LIVE policy change:** HOLD. This branch has not changed any deployment, broker order, risk budget or execution configuration.
- **Next properly independent gate:** preregistered candidate(s), sealed forward period beyond 2026-10-30 with complete fresh SIP and next-session labels, realistic bid/ask spread model / market impact, explicit risk limit and combined portfolio validation, plus corrections/late print and split audit. Multiple-testing controls. No tuning on evaluated test labels.

## Unresolved limitations

2025 and 2026 historical data were examined before these tests, so conventional OOS language is not justified for future strategy selection. Entry at printed 09:30 open is a simulation assumption; real next-open execution and 5bp assumed slippage are not validated against actual fills. MDD is daily-mark-to-market on close, not peak-to-trough intrabar excursion. Days in cash earn zero. 'Always intraday long' baseline enters and exits **daily** and incurs daily roundtrip costs, and is not continuous buy-and-hold. Separate per ticker P&L cannot be summed without a cross-ticker allocation and correlation model.

**Source files:** `us_multisymbol_volume_calibration.py`, `test_us_multisymbol_volume_calibration.py`, `us_multisymbol_volume_trade_backtest.py`, `test_us_multisymbol_volume_trade_backtest.py`, `.github/workflows/kalman-us-multisymbol-bars.yml`.
