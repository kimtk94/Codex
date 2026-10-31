# QLD 40-axis joint execution-policy research (2026-10-31)

## Research contract

Only **QLD**, after NYSE close signals, next-eligible session entry, historical Alpaca SIP adjusted all 15-minute OHLC. The original benchmark is TP +3%, SL -3%, hold 4 NYSE sessions, 10 bp each side. All calculations are isolated read-only; LIVE execution is unchanged.

The 40 axes intentionally include options with very small or uncertain effects. Every **configuration is evaluated as a whole portfolio**, not an additive ranking of individual option improvements. Original price-only and integrated-regime classifier probabilities are computed once per yearly walk-forward fold, then the same 800 policy vectors are applied separately to both models and both 2025 and 2026. 2026 ends 2026-10-30.

### Forty parameters

| # | Axis | Meaning |
|---|---|---|
| 1 | `tp` | Full take-profit threshold |
| 2 | `sl` | Fixed stop-loss threshold |
| 3 | `hold` | Maximum NYSE sessions after entry |
| 4 | `entry_delay` | Number of completed 15m opening candles before entry |
| 5 | `size` | Maximum portfolio cash allocation |
| 6 | `risk_budget` | Position cap from nominal stop distance |
| 7 | `split` | Single entry or initial/reserve split ratios |
| 8 | `add_dip` | Reserve entry limit-price drawdown |
| 9 | `add_deadline` | Final intraday bar for reserve order |
| 10 | `partial_tp` | Fraction of remaining position to sell at partial target |
| 11 | `partial_at_r` | Partial take-profit in initial risk units |
| 12 | `trail` | Trailing-stop distance |
| 13 | `trail_start_r` | Trail activation in initial risk units |
| 14 | `breakeven_r` | Breakeven activation in risk units |
| 15 | `be_offset_bps` | Stop offset after breakeven activation |
| 16 | `cooldown` | NYSE sessions blocked after a full exit |
| 17 | `vix_min` | Lower VIX regime bound (prior-session VIX) |
| 18 | `vix_max` | Upper VIX regime bound |
| 19 | `trend` | QQQ positive 5d/20d trend gating |
| 20 | `qld_r5_gate` | QLD positive/negative 5d return direction |
| 21 | `vol_cap` | QQQ realized-volatility maximum |
| 22 | `confidence` | Classifier probability selection threshold |
| 23 | `slippage_bps` | Extra assumed execution slippage each side |
| 24 | `max_month` | Limit new trades per NY-local calendar month |
| 25 | `gap_cap` | Entry price above signal-day QLD close cap |
| 26 | `entry_session_offset` | Enter 1/2/3 sessions after signal |
| 27 | `gap_down_cap` | Entry price below signal-day close cap |
| 28 | `gap_up_floor` | Minimum entry appreciation vs signal close |
| 29 | `vol_floor` | QQQ realized-volatility minimum |
| 30 | `qqq_r20_cap` | Upper bound on 20-session QQQ momentum |
| 31 | `qqq_r5_cap` | Upper bound on 5-session QQQ momentum |
| 32 | `qld_r5_abs_cap` | Maximum absolute QLD 5-session move |
| 33 | `credit_floor` | Lagged HYG-minus-LQD return spread minimum |
| 34 | `credit_cap` | Lagged credit return spread maximum |
| 35 | `tnx_cap` | Lagged 10-year Treasury yield proxy maximum |
| 36 | `vix_change_cap` | Lagged five-session VIX rate of change maximum |
| 37 | `smh_spy_floor` | Lagged SMH-minus-SPY 20-session relative return minimum |
| 38 | `min_rr` | Minimum nominal TP/SL ratio; invalid combos rejected |
| 39 | `prior_bar_range_cap` | Maximum price range of last **completed** candle before entry |
| 40 | `min_profit_holding_bars` | Bars before take-profits allowed; hard stop never delayed |

The full unconstrained Cartesian product has **188,480,052,303,590,546,472,960** raw parameter vectors. Some are invalid (e.g., minimum nominal reward/risk not met, reversed min/max bounds) or equivalent (e.g., unused partial TP settings when partial selling disabled). We do **not** claim exhaustive coverage of this space. Round 1 samples 800 deterministic, multi-axis vectors and evaluates 800 × 2 models × 2 test years = **3,200 portfolio simulations**. The same 800 combinations are evaluated across all four cohorts. A separate pairwise-coverage diagnostic measures how many distinct two-parameter level pairs were actually exercised.

## Integrity gates and limitations

- **Every policy replays full entry/stop/add/partial-exit/cooldown/cash position state**, rather than summing separately measured option effects.
- No borrowing, no overlapping positions, nominal 10 bp each side, explicit additional slippage. Cannot assume execution at midpoint for unobserved quotes.
- If SL and TP can both execute in the same OHLC bar, prioritize SL. Stop updates based on highs are only active the following 15m bar. No imputation of missing candles.
- Same-bar pending limit order and subsequent price path are ambiguous with OHLC; treating a touched limit price as executable is still an optimistic model assumption. **Do not use to promote LIVE** without tick/trade-order and order book/slippage validation.
- Interactions are descriptive difference-in-differences contrasts averaged over randomly co-varying other knobs, not causal estimates. They are subject to sparse cells and multiple comparisons.
- **Policy selection on 2025/2026 creates data snooping.** All 800 outcomes are exploratory, no independent untouched test sample. Neither a winner nor 100 repetitions demonstrate LIVE suitability.
- Prior **100 repeated training runs remain a separate training-uncertainty check**. The current 800 × four scenario evaluation reuses a single fixed walk-forward model per year and model type. Do not conflate the counts.
- `joint_report.py` requires 800 unique IDs, both test years and both signal models for every configuration; missing shards or cohort rows cause failure.
- Large-search findings should be validated in a **new**, independent post-selection period before changes to LIVE.

CI workflow: [Kalman QLD Joint 40 Option Interactions](../../.github/workflows/kalman-qld-joint-options.yml). Original fixed-rule model investigation remains [PR #477](https://github.com/kimtk94/Codex/pull/477).
