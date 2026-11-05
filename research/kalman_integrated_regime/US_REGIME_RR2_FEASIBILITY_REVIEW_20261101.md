# Kalman Net R:R >=2.0 — Historical Feasibility and Regime-Conditioned Trade Review

**Analysis completed:** 2026-11-01 (KST). **Status:** **research-only, NO LIVE promotion**.  
**Source:** Alpaca SIP 15m, 2024-01-01—2026-10-30, five equities/ETFs SPY/IWM/SMH/MU/COIN, fully observed RTH.  
**GitHub Actions:** [#41217666574](https://github.com/kimtk94/Codex/actions/runs/41217666574) **contracts PASS + full historical SIP PASS**.  
**Aggregate artifact:** [Google Drive ZIP](https://drive.google.com/file/d/1-uxzHk0xtiIX3G_SvJqKBFvp-LOf-fvF/view?usp=drivesdk). Private raw licensed SIP bars were deleted on ephemeral runner; outputs contain only derived statistics.

## Objective and constraints

User requirement: **BEFORE each trade, reject any candidate whose planned NET reward-to-risk is below 2.0**, after commission + assumed slippage. No changing this threshold and no knowingly unrealistic targets to make a trade appear admissible. Regime classifications must be independent from historical trading P&L; conditional trade returns and realized R are evaluated *after* regime assignment.

Baseline signal: price-3 versus price+RVOL/zscore-5, unweighted logistic trained on prior years only, T close signal, conditional next-day 09:45 15-minute-bar opening-price entry. T's completed 14-day ATR, 30bps total roundtrip costs, gross stop [0.5%,3%], gross target <=8%, 1/2/4-day max hold, no overlapping position per ticker, conservative stop-first within an ambiguous 15-minute candle. Gap-through-stop simulated at later candle open. Bull/Bear/Transition proxy uses SPY 50-day moving average, its 10-day slope, and SPY 20-day return at T close only.

### Before-outcome analytic geometric feasibility

| Research case | Stop / target in ATR units | ATR divided by candidate entry-price range where RR>=2 and stop/target width limits possible |
|---|---|---|
| BASE | 1.25 / 3.00 | 1.8%-2.4% |
| MODERATE | 1.00 / 2.50 | 1.8%-3.0% |
| TIGHT | 0.75 / 2.25 | 1.2%-3.56% |

These are **fixed risk geometry alternatives**, not fitted to maximize returns. All three KEEP the strict required **NET R:R >=2.0**, not 1.5 or gross R:R 2.0.

## Key diagnostic result: why COIN accepts no trades

For the V price+volume arm:

| Year | Proposed direction entries | BASE admitted | MODERATE admitted | TIGHT admitted | Ex ante reason for all rejects |
|---|---:|---:|---:|---:|---|
| 2025 Jan–Oct | 80 | 0 | 0 | 0 | **STOP_TOO_WIDE** (80 under each geometry) |
| 2026 Jan–Oct | 46 | 0 | 0 | 0 | **STOP_TOO_WIDE** (46 under each geometry) |

The all-or-nothing rejection is **not** an absence of direction signals and **not** a measured failure of the RR>=2 criterion itself: the entire candidate set violates the current **max 3% gross stop-distance condition** for the particular three ATR widths. Wider volatility instruments may need a *different research risk budget*, with correspondingly smaller position sizes and realistic stop-fill probabilities; do NOT silently increase live stop width, relax risk budgets or assert that wider stops would be profitable.

## One-session net portfolio outcomes

Each symbol receives an independently compounding **20% of initial capital**, without rebalancing across sleeves. Values are historical modeled **net** returns with 30bps total roundtrip.

| Geometry | 2025 Jan–Oct | 2026 Jan–Oct |
|---|---:|---:|
| BASE net R:R2 | **−4.7908%** | **−1.0301%** |
| MODERATE net R:R2 | **−5.0500%** | **−4.1169%** |
| TIGHT net R:R2 | **−8.7413%** | **−7.1637%** |
| BASE net R:R2 + BULL-only | −2.3661% | −2.1377% |
| MODERATE net R:R2 + BULL-only | −3.0325% | −2.6113% |
| TIGHT net R:R2 + BULL-only | −6.1608% | −5.1186% |

BULL state did not consistently improve results enough to infer a profitable Bull-gated strategy. There is no evidence supporting use of this prototype as a live trade-entry rule.

### Why loosening stop geometry did not help

- **IWM 2025:** BASE 25/72 candidate signals admitted, 23 executed, net **−2.9403%** with **0 stop-out events** (23 timed exits). TIGHT 60/72 admitted, 58 executed, net **−1.9225%**, **10 STOP +1 TARGET +47 TIME_CLOSE**, daily-close MDD **−12.94%**. **IWM 2026**: BASE 27/57 admitted, net −0.365%; TIGHT 50/57 admitted, net −4.858%, **10 STOP, 40 TIME_CLOSE**.
- **SMH 2025:** BASE 29/112 admitted, 28 executed, net −14.457%. TIGHT 88/112 admitted, 86 executed, net **−22.976%** with 17 STOP, 1 STOP_GAP, 68 TIME_CLOSE. **SMH 2026:** BASE 17/155 admitted, net −4.785%; TIGHT 100/155 admitted, 97 executed, net −16.739%, 14 STOP.
- **SPY 2026:** BASE and MODERATE 0 accepted of 143 proposed; TIGHT 49 admitted, **−14.222%** net with 10 STOP and 39 TIME_CLOSE.
- **MU 2026:** 186 proposed V signals; BASE and MODERATE 0 admitted, TIGHT also 0 (184 gross stop width violations, 2 target-distance violations).
- More admitted trades did not result in higher realized positive expected R. It increased exposure to negative-expectancy trades in the evaluated history.

### Why extending holding time alone cannot be chosen on these data

Five-sleeve V model, ungated Bull filter OFF, all requiring net R:R>=2.0:

| Geometry | 2025 1D / 2D / 4D | 2026 1D / 2D / 4D |
|---|---|---|
| BASE | −4.79% / −3.32% / −0.70% | −1.03% / −0.64% / +0.49% |
| MODERATE | −5.05% / −1.06% / +2.20% | −4.12% / −5.72% / −4.27% |
| TIGHT | −8.74% / −0.29% / +3.59% | −7.16% / −3.29% / −2.55% |

A few retrospective 4-session profits are not stable across years/configurations, and the examined years are already affected by repeated model/feature research selection. Do not promote the best case.

## Conclusions and next mandatory research gate

1. The **net R:R>=2.0 hard entry veto is implemented and verified** by both regression contracts and full historical data processing.
2. Ex ante geometric R:R is **necessary but not sufficient**: the exit can be TIME_CLOSE, a gap stop may exceed planned loss, and a gross target can have low target-first probability. A directional one-day classifier is not a target-before-stop classifier.
3. COIN needs **risk-distance and sizing research**, not indiscriminate TP increases: report ATR/price, expected gap risk and position sizing under constant **portfolio risk per trade**, with an explicit no-trade option. Any >3% stop limit requires a **separate user-approved candidate policy**, not a silent rule change.
4. Regime should be validated separately on market-state stability, transitions, conditional market risk/volatility and label availability; avoid using realized strategy P&L to set market state labels.
5. The 2025/2026 years are heavily consulted; require **preregistered untouched forward outcomes** and broker-realistic fills before even considering LIVE promotion.

**Code:** `research/kalman_integrated_regime/us_regime_rr2_feasibility.py` and `test_us_regime_rr2_feasibility.py`, integrated in `.github/workflows/kalman-us-multisymbol-bars.yml`. No live broker, capital allocation or execution settings changed.
