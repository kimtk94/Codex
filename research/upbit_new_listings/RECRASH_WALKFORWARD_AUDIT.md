# Upbit post-crash 4h re-crash walk-forward audit

Read-only experimental model; do not deploy to live.

Source: upbit_crash_end_recrash_audit.csv (167 entry events); evaluated in chronological expanding-year folds using logistic regression C=0.3, median imputation and StandardScaler fit on training only.

Features observable at entry: crash_to_entry_h, pre_4bar_net_pct, higher_lows, last_close_over_prev_high, turnover_acceleration, turnover_cooling.
Target: 4-hour minimum low after entry <= -3% relative to entry (recrash_4h).

| Evaluation year | training n | evaluation n | recrash rate | AUC | Brier |
|--|--:|--:|--:|--:|--:|
| 2025 | 27 | 80 | 76.25% | 0.6031 | 0.1855 |
| 2026 | 107 | 60 | 56.67% | 0.3812 | 0.3017 |

2026 if predicted re-crash risk < 0.6: 9 trades, 55.56% actually re-crashed, mean trading net return -2.6459%. Unfiltered 60 trades mean -0.1811%; cutoffs < 0.4 and <0.5: no trades.

Interpretation: No robust predictive skill on 2026; do not deploy or use model for BUY decisions. Dataset preselected on entry conditions; inference cannot generalize to all listing candles. Re-use of 2026 exploratory data is not a fresh independent holdout. Missing delisted listings, bar-level fills not authenticated.
