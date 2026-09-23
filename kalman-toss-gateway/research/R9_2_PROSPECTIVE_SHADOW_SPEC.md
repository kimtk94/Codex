# Kalman R9.2 — Prospective GDELT NGram Attention Shadow

**Pre-registered:** 2026-09-23  
**Mode:** RESEARCH_ONLY / FORWARD_ONLY  
**Champion/LIVE:** R5.1 unchanged  
**Earliest prospective signal:** 2026-09-24 13:30:00 UTC

## 1. Motivation

R9.1 was not eligible for alpha promotion because its pre-registered temporal-consistency and bootstrap-significance gates failed.

R9.1 nevertheless showed a large favorable historical headline effect versus both the window-matched base and frozen R5 replay. R9.2 therefore does not retune R9.1. It asks one new question:

> Do the exact frozen R9.1 NGram attention features continue to add value on genuinely new post-freeze data?

No R9.1 result is re-fit, re-scored, re-thresholded, or re-selected.

## 2. Frozen information source

The model input source remains exactly:
- GDELT BigQuery Web 1Gram
- GDELT BigQuery Web 2Gram
- ENGLISH
- exact frozen company alias equality
- frozen 93-symbol registry

The following are **not substitutes** for R9 model input:
- GDELT DOC article counts
- RSS article counts
- SEC events
- news sentiment
- LLM labels
- title novelty

`news_ingest_v1` may be used for operational observability/coverage only. Its article-count fields cannot replace Web NGram COUNT.

If the Web NGram source is unavailable or quota-blocked, R9.2 fails closed and emits no new model signal.

## 3. Frozen R9 feature contract

Exactly three features, unchanged from R9.1:
- `ngram_log1p_d1`
- `ngram_log1p_7d`
- `ngram_abnormal_z_30d`

Calendar-missing symbol/day observations are completed to zero only after a successful source extraction for that completed UTC day.

PIT rule:
- `signal_as_of = timestamp + 60 minutes`
- `news_day_used = DATE(signal_as_of) - 1 UTC day`
- same UTC day news is forbidden
- future news is forbidden

A shadow signal is blocked unless the NGram source state confirms completeness through `news_day_used`.

## 4. Historical bridge versus prospective evidence

Historical research source ends at 2026-09-02 00:00:00 UTC exclusive.

The interval from 2026-09-02 through the day before the first R9.2 signal may be collected solely to maintain the rolling NGram feature state.

Those bridge days:
- may populate mention history;
- may populate feature snapshots;
- may not create R9.2 signals;
- may not create R9.2 trades/outcomes;
- may not be used to change features, model parameters, or gates.

The first eligible R9.2 signal is no earlier than `2026-09-24T13:30:00Z`.

## 5. Frozen prospective model

R9.2 freezes exactly one HGB model before the first prospective signal.

Training data:
- same frozen R5 target: `relative_ret_4b`
- same R5 base feature formulas
- the three frozen R9 NGram features
- feature-ready rows from 2024-09-01 onward
- target timestamp strictly before 2026-09-02 13:30 UTC
- no post-cutoff outcomes

Model template:
- clone the already-frozen R5 HGB architecture
- no hyperparameter search
- no feature search
- one final fit only
- artifact and medians are SHA256-locked

After freeze, refit is prohibited.

## 6. Canonical live equity features

R9.2 does not fetch a second equity market feed.

It reads the canonical files already maintained by Daily Ops:

`frozen canonical_history_v1 + r4_live_canonical_v1 overlay`

It reproduces the existing R5.1 feature contract exactly:
- gap-safe 60m rolling features
- QQQ context
- cross-sectional ranks
- beta/residual features
- four frozen interactions

The same historical R1 reconciliation remains fail-closed.

Minimum eligible universe coverage remains 90 of 93 symbols.

## 7. Shadow selection/execution

Candidate id: `R9P_NGRAM_ATTENTION_FROZEN`

For every eligible post-boundary timestamp:
- score all eligible symbols with the frozen R9.2 model;
- select Top1;
- compute the same R4 volatility-target weight;
- set `live_execution=false`;
- set `production_promotion=false`;
- never write production `strategy_signal`;
- never submit a broker order.

A separate non-overlap research ledger uses:
- 10 bps cost
- exact +4 expected-seq outcome
- same execution semantics as R5.1 historical/prospective research.

## 8. Paired R5.1 diagnostic

On the exact R9.2 eligible rows, also replay the already-frozen R5.1 HGB score.

Store:
- R9 Top1
- R5.1 Top1
- Top1 agreement
- score Spearman correlation
- Top10 overlap
- both volatility-target weights

A common non-overlap cadence evaluates both selections on the same entry timestamps and exact +4 expected-seq exits.

This diagnostic does not alter R5.1.

## 9. Evidence gates

Minimum review gate:
- >=100 mature R9 outcomes
- >=60 distinct entry trading days

Preferred confirmation gate:
- >=150 mature R9 outcomes
- >=90 distinct entry trading days

When minimum review is reached, compute a 5-day moving-block bootstrap for paired daily:

`log(1 + R9 net10 return) - log(1 + R5.1 net10 return)`

Prospective statistical confirmation requires:
- paired bootstrap 95% CI lower bound > 0
- one-sided p < 0.05
- positive cumulative paired log-growth difference

These conditions only establish prospective research confirmation. They do **not** automatically enable LIVE trading.

## 10. Governance

Frozen after first prospective signal:
- NGram aliases
- NGram feature definitions
- rolling windows
- model
- imputation medians
- Top1 selection
- volatility sizing
- 10 bps cost
- +4 horizon
- evidence gates

Forbidden:
- backfilling R9.2 signals before the prospective boundary;
- replacing NGram COUNT with article count;
- refitting after observing prospective outcomes;
- selecting only favorable regimes after observing outcomes;
- changing production/LIVE based on intermediate shadow results.

## 11. Storage

Durable source/feature/evidence state is isolated under Neon `research` tables and Drive research artifacts.

Drive root:
`US_ETF/model_lab_v1/results/r9_2_prospective_shadow`

Expected artifacts:
- `model_freeze/r9_2_hgb.joblib`
- `model_freeze/r9_2_training_medians.json`
- `model_freeze/r9_2_model_freeze_manifest.json`
- `r9_2_signal_log.parquet`
- `r9_2_trade_entry_log.parquet`
- `r9_2_outcome_log.parquet`
- `r9_2_r5_paired_signal_log.parquet`
- `r9_2_r5_paired_outcome_log.parquet`
- `r9_2_status.json`
- `r9_2_run_log.jsonl`

Production invariant:
- R5.1 unchanged
- LIVE orders unchanged
- sizing unchanged
- exits unchanged
- production `strategy_signal` unchanged
- auto-trade policy unchanged
