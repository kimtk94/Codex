# R5.1 Conditional LIVE Freeze — 2026-10-03

Status: **FROZEN FOR LIVE OPERATIONS**

Freeze label: `R5.1_CONDITIONAL_LIVE_FREEZE_20261003`

Repository: `kimtk94/Codex`  
Working branch: `research/r5-1-topk-portfolio-20261002`  
Freeze baseline commit: `2f26e03efb1cbb1e4ae00aedb70dca9df147f03b`

## 1. Scope

This freeze covers the US R5.1 conditional LIVE execution policy only. It does not promote unrelated research work to `main`, and it does not change the frozen R5.1 model selection.

Frozen strategy version:

- `R5.1_BASE_HGB`
- execution policy: `R5_LIVE_CONDITIONAL`
- execution mode: `LIVE`
- total conditional budget per signal: KRW 20,000
- pyramiding: disabled
- target exit: FIXED_4
- Friday-flat: enabled
- Friday-flat buffer: 15 minutes before US fractional-order end

## 2. Frozen conditional allocation

Thresholds frozen for this deployment:

- relative gap threshold: `0.08156846590660159`
- Rank1 confidence threshold: `0.00041106678948450823`

Decision precedence:

1. LOW_CONFIDENCE
2. CLOSE_GAP
3. TOP1_ONLY_WIDE_GAP

Allocation:

| Regime | Condition | Allocation |
|---|---|---|
| LOW_CONFIDENCE | Rank1 score <= confidence threshold | Rank1 KRW 10,000 + Cash KRW 10,000 |
| CLOSE_GAP | confidence passes and relative gap <= gap threshold | Rank1 KRW 10,000 + Rank2 KRW 10,000 |
| TOP1_ONLY_WIDE_GAP | confidence passes and relative gap > gap threshold | Rank1 KRW 20,000 |

Relative gap:

`(Rank1 score - Rank2 score) / abs(Rank1 score)`

## 3. Score handoff contract

The executor resolves conditional ranking context in this order:

1. signal payload score/ranking if present;
2. same-run `strategy_signal` rows if sufficient;
3. native Kalman web snapshot fallback.

Native snapshot contract:

- `model_as_of_utc`
- `today_selector.selected_symbol`
- `today_selector.model_score`
- `model_universe[SYMBOL].model_score`

The native snapshot universe is sorted by `model_score` descending. The snapshot is accepted only when:

- sorted Rank1 equals `today_selector.selected_symbol`;
- Rank1 equals the LIVE signal symbol;
- snapshot model timestamp equals the LIVE signal timestamp;
- selected score is consistent with the sorted Rank1 score.

If required score context is unavailable, execution fails closed:

- `CONDITIONAL_SCORE_MISSING_RANK1`
- `CONDITIONAL_SCORE_MISSING_RANK2`

No deterministic Top1-full-size fallback is permitted after this freeze.

## 4. Entry safety contract

### Model-cycle locking

The hourly US model cycle owns `us-cycle.lock`.

The execution watcher must still run risk management while the model pipeline is busy:

- `position_manager` runs under the execution lock;
- risk exits are not blocked by `us-cycle.lock`;
- only the new-entry phase is skipped when `us-cycle.lock` is busy;
- expected log marker:
  `EXECUTION_ENTRY_SKIP_UTC=... reason=US_CYCLE_LOCK_BUSY risk_manager=COMPLETED`.

### Friday-flat entry gate

Friday entry requires both:

1. effective signal/actionable time < safe exit deadline;
2. actual execution check time < safe exit deadline.

Otherwise the entry is blocked. A late execution must report:

- `FRIDAY_EXECUTION_AFTER_SAFE_DEADLINE`
- readiness reason: `FRIDAY_ENTRY_WINDOW_CLOSED`

This prevents a model pipeline that finishes late from opening a new position after the Friday-safe entry cutoff.

## 5. Exit safety contract

`position_manager` remains authoritative for managed-position exits, including:

- stop loss;
- take profit;
- profit-to-loss flip;
- max-hold / target-exit management;
- Friday-flat.

The watcher risk phase must continue even if the hourly model pipeline is still running.

## 6. Verified live incidents and fixes

### MU Friday-flat

MU was closed successfully by Friday-flat:

- exit reason: `FRIDAY_FLAT`
- state: `CLOSED`

### ORCL late-entry race

A delayed pipeline caused an ORCL entry after the Friday-safe deadline before the actual-execution-time check existed. ORCL was subsequently closed by `FRIDAY_FLAT`.

The freeze includes the corrective execution-time gate so this late-entry path is blocked going forward.

## 7. Verified conditional cases

Synthetic validation passed for all three branches:

- LOW_CONFIDENCE -> Rank1 KRW 10,000 + Cash KRW 10,000
- CLOSE_GAP -> Rank1 KRW 10,000 + Rank2 KRW 10,000
- TOP1_ONLY_WIDE_GAP -> Rank1 KRW 20,000

A real native snapshot score handoff was also validated:

- Rank1: BA
- Rank1 score: `0.0006136439258906945`
- Rank2: DE
- Rank2 score: `0.0005314615217972279`
- relative gap: `0.1339252302940669`
- decision: `TOP1_ONLY_WIDE_GAP`
- allocation: BA KRW 20,000

## 8. Freeze-critical files

The following files are freeze-critical:

- `engine/r5_conditional_policy.py`
- `engine/r5_conditional_live.py`
- `engine/auto_trade.py`
- `engine/position_manager.py`
- `app/readiness.py`
- `scripts/run_execution_watch.sh`
- `scripts/run_auto_trade.sh`
- `scripts/run_us_cycle.sh`
- `scripts/configure_auto_trade_env.sh`
- `scripts/apply_live_conditional_20000.sh`
- `tests/test_r5_conditional_policy.py`
- `tests/test_r5_conditional_live_snapshot.py`

## 9. Required revalidation before changing LIVE behavior

Any change to a freeze-critical file requires re-running this checklist before deployment:

- [ ] Python compile succeeds using an environment with required runtime dependencies.
- [ ] gateway health returns `status=ok`.
- [ ] `signalPolicy=R5_LIVE_CONDITIONAL`.
- [ ] conditional confirmation is true.
- [ ] gap threshold equals frozen value.
- [ ] confidence threshold equals frozen value.
- [ ] native snapshot Rank1/Rank2 score extraction succeeds.
- [ ] stale or timestamp-mismatched snapshot is rejected.
- [ ] Rank1-symbol mismatch is rejected.
- [ ] missing Rank1 score blocks entry.
- [ ] missing Rank2 score blocks entry when Rank2 is required.
- [ ] LOW_CONFIDENCE allocates 10k / 10k cash.
- [ ] CLOSE_GAP allocates 10k / 10k.
- [ ] WIDE_GAP allocates Rank1 20k.
- [ ] Friday after-safe-deadline entry is blocked.
- [ ] watcher runs risk manager while model cycle lock is busy.
- [ ] no active unmanaged broker holdings exist before enabling new entry.
- [ ] no unexpected open BUY orders exist.
- [ ] trade mirror reflects the broker state.

## 10. Operational change policy

After this freeze:

- LIVE behavior changes should be developed and tested on a separate research branch.
- Do not silently alter thresholds, allocation, Friday-flat timing, score semantics, or lock ordering.
- A change to any of those items creates a new freeze version.
- Historical backtest improvements do not automatically modify this LIVE freeze.
- Do not infer deployability from research CAGR alone; execution overlap, cash usage, order windows and broker behavior remain separate operational constraints.

## 11. Known operational dependencies

- Google Drive/rclone mount must be healthy for the snapshot fallback path.
- rclone FUSE may show metadata-level `Input/output error` while Python file reads still succeed; content-read validation is authoritative for this path.
- system Python may not include `psycopg`; runtime tests that import LIVE executor modules should use `/opt/kalman/.venv/bin/python`.
- LIVE `load_signal` enforces signal freshness; offline/frozen score validation should test the snapshot parser directly rather than weakening the LIVE freshness gate.

## 12. Freeze acceptance

The freeze is accepted when the repository contains this manifest and the verifier script passes the static/runtime checks appropriate to the server environment.

Do not modify this document in-place to describe a behaviorally different LIVE policy. Create a new freeze document/version instead.
