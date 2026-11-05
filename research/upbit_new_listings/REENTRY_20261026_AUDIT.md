# Re-entry audit (2026-10-26)
Local replay: github artifact 12555802314, 190 full KRW cohorts, code file reentry_audit.py. Uses per-bar causal entry confirmation: post-high >=20% drawdown, >=4 completed bars no new low, >=3% recovery, volume/range cooling, price proxy-VWAP. Entry within UTC 24h after first observed bar. Post-exit state resets; NEW 20% crash required before next entry. One trading slot per coin; up to 1/2/3 consecutive entries. Fixed +20% TP/-3% SL vs 10% trailing with -3% initial stop. Fees 0.05% and assumed slippage 0.15% each direction; stop-first intrabar.
| exit | max entries | train n | train mean per trade % | 2026 n | 2026 mean per trade % |
|---|---:|---:|---:|---:|---:|
| fixed | 1 | 74 | -0.7620 | 43 | -0.0410 |
| fixed | 2 | 81 | -0.9764 | 46 | -0.2498 |
| fixed | 3 | 82 | -1.0040 | 46 | -0.2498 |
| trail | 1 | 74 | +0.8743 | 43 | -0.3533 |
| trail | 2 | 82 | +0.4896 | 46 | -0.5417 |
| trail | 3 | 83 | +0.4446 | 46 | -0.5417 |
Interpretation: repeat-entries worsened results, no mean +20% achieved, no live authorization. First-entry counts 74/43 differ from older 77/45 due to fresh-crash state reset and warm-up. Results on 2026 are exploratory and reuse repeatedly inspected data, not independent holdout. No delisted-coins and no real order-book fills. No portfolio MDD estimate.
