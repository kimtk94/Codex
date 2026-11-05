# Upbit New Listings 15m — 2026-10-24 full-run audit

Source: GitHub Actions run [40081400856](https://github.com/kimtk94/Codex/actions/runs/40081400856), artifact 12555802314.

## Population
- Current KRW markets scanned: 299
- New KRW first-trade candidates since 2023-10-24 still listed: 201
- Complete seven-day candidate cohorts (>=600 printed 15-minute bars): 190
- Downloaded minute bars: 130,559
- API failed markets: 0
- 4 incomplete and 7 sparse; delisted markets not reconstructed.

## Fixed user policy
Enter at open of 15-minute candle index 4 (60 minutes after first observed listing candle);
take profit +10%, stop -3%, seven calendar days maximum. Assumed entry/exit
slippage 0.15% each and fee 0.05% each, candle stop-first if both touched.

| Year | n | Win % | Mean net % |
|---|---:|---:|---:|
| 2023 | 3 | 0.0 | -3.242 |
| 2024 | 33 | 24.242 | -0.349 |
| 2025 | 84 | 11.905 | -1.660 |
| 2026 (held out) | 70 | 10.000 | -2.185 |

2026 exits: 63 stop, 5 take-profit, 2 expiry; 7 net-positive exits (including non-take-profit).
Train 2023-25: 120 trades, mean -1.3393%, 15% net wins.
Total: 190 trades, 25 winners (13.16%), mean -1.6509%.
Median trade return -3.2423%.

## First-hour, pre-entry filter robustness (exploratory, no model selected)
| Predetermined filter | Train n | Train mean % | 2026 test n | 2026 mean % |
|---|---:|---:|---:|---:|
| Unfiltered fixed policy | 120 | -1.339 | 70 | -2.185 |
| First hour positive return | 106 | -1.577 | 52 | -1.995 |
| First hour non-positive return | 14 | +0.463 | 18 | -2.733 |
| First-hour high/low range <20% | 18 | -2.082 | 29 | -2.032 |
| At least three green 15m candles in first hour | 21 | -0.155 | 10 | -1.946 |

Caution: These are exploratory slice checks; uncorrected multiple comparisons.
None demonstrates a positive 2026 held-out mean. Do not deploy live.

## Blockers to robust portfolio backtest
1. Missing formerly-listed / delisted market cohorts => survivor bias.
2. Listing timestamp proxied by first observed candle; market-specific opening delays and candle gaps.
3. Intrabar trigger ordering and queue-dependent fills unknown; slippage is only an assumption.
4. No simultaneous-position-capital schedule => portfolio CAGR and portfolio MDD not available.
5. Data selection includes only >=600 observed 15m candles; the missing/illiquid cohort may be systematically different.
6. Fixed analysis dataset ends 2026-10-24; last seven days of new listings excluded as incomplete.
