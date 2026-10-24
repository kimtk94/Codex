# Kalman TSLA non-overlapping staggered entry: first empirical audit

- Source: GitHub Actions run 40080142190, artifact 12555356113 (`nonoverlap.csv`, `minute_profile.json`).
- Period: 2023-01-13 13:11 UTC to 2023-01-17 21:02 UTC. 784 actual bars; 776/783 adjacent pairs are 60 seconds; 7 longer gaps.
- Parameters: TP=3%, SL=3%, 5bps each side. Staggered legs are modeled as equal-share legs rather than fixed-KRW notional legs.
- Research simulation only: **no R5.1/R5.2 entry signals, no walk-forward, no capital constraints, no portfolio MDD**.
- Beware 5/10/20/40/60/100/120/180/240 min horizons sample counts: 155/77/38/18/11/6/5/3/2. All horizons over 60 min have fewer than 10 non-overlapping observations.
- Selected 1-minute spacing comparisons from artifact (mean return %):

| Horizon | 1 leg | 2 legs | 3 legs | 5 legs | Samples |
|---|---:|---:|---:|---:|---:|
| 5m | -0.04754 | -0.05505 | -0.06897 | -0.08284 | 155 |
| 20m | 0.12019 | 0.10473 | 0.08482 | 0.06221 | 38 |
| 60m | 0.64458 | 0.62706 | 0.57283 | 0.55004 | 11 |
| 100m | 1.42611 | 1.44949 | 1.33234 | 1.32634 | 6 |
| 120m | 1.70755 | 1.70664 | 1.55070 | 1.49954 | 5 |
| 180m | 2.34092 | 2.33570 | 2.16091 | 2.10249 | 3 |
| 240m | 2.89705 | 2.89705 | 2.89705 | 2.89705 | 2 |

## Decision

**No candidate selected / no live change.** The longer-horizon apparent gain is not reliable because valid non-overlapping observations collapse with horizon length and the sampled days are too narrow. The matching 240m values across 1–5 legs warrant checking fill/exit paths before interpretation.

## Next gate

1. Expand minute dataset across many days, symbols and market regimes while preserving private source access.
2. Compare equal-notional staggered legs using actual cash accounting, intrabar order conventions and no simultaneous allocation conflicts.
3. Add non-overlapping out-of-sample evaluation by chronological days/folds; report bootstrap uncertainty and minimum independent sample requirements.
4. Distinguish per-window profitability from portfolio equity returns, exposure, and MDD.
5. Publish only aggregated, validated metrics to dashboard. No changes to live execution.
