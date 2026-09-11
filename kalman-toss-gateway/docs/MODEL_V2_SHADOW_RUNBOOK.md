# Kalman Model V2 — Feature Matrix, Candidate Model, SHADOW Runbook

Status: research / file SHADOW + optional guarded Neon mirror

Neon write: disabled by default; SHADOW mirror only when explicitly enabled

Toss execution: none

Automatic retraining: none

## 1. Purpose

Market Tools V2 data is connected into one reproducible research lineage:

    Market Data V2
      -> TA-Lib V2
      -> Feature Matrix V2
      -> Candidate Model
      -> JSON Artifact
      -> Fixed-model SHADOW

The frozen Unified production model is not modified.

## 2. Versions

    model version   : kalman_model_v2_001
    dataset version : kalman_feature_matrix_v2_001
    feature set     : market_tools_v2_001

Configuration source:

    config/model-v2-spec.json

## 3. Target markets

US anchor is SPY. The target is 5 anchor observations forward return greater
than zero. Strategy version is KALMAN_V2_US_LOGIT_001.

KR anchor is KOSPI. The target is 5 anchor observations forward return greater
than zero. Strategy version is KALMAN_V2_KR_LOGIT_001.

BTC anchor is BTC-USD. The target is 7 anchor observations forward return
greater than zero. Strategy version is KALMAN_V2_BTC_LOGIT_001.

## 4. Leakage policy

Cross-market features use explicit observation lags.

US decision:

    US      lag 0
    COMMON  lag 0
    BTC     lag 1
    KR      lag 0

KR decision:

    KR      lag 0
    BTC     lag 0
    US      lag 1
    COMMON  lag 1

BTC daily decision:

    BTC     lag 0
    KR      lag 0
    US      lag 1
    COMMON  lag 1

The conservative lags are intentional because source timestamps are daily
dates rather than complete close-time provenance.

## 5. Matrix features

Raw price levels are not model features. Each asset produces stationary or
relative features:

    ret1
    ret5
    ret20
    vol20
    z20
    ma20_gap
    ma50_gap
    rsi_centered
    macd_pct
    macd_hist_pct
    adx01
    atr_pct
    natr01
    roc10_01
    bb_pctb
    obv_z20

Group aggregates add median, coverage, and where meaningful positive-ratio
features for US, KR, BTC, and COMMON groups.

## 6. Finviz policy

Finviz is not a V2_001 time-series model feature.

The point-in-time archive is currently too short, and historical screener
backfill would introduce look-ahead risk. Finviz remains a stock discovery
and candidate-universe layer until enough real daily snapshots accumulate.

## 7. Matrix output

Default root:

    /mnt/gdrive/Market_Model_V2/

Matrix artifacts:

    matrices/us_matrix.parquet
    matrices/us_matrix_manifest.json
    matrices/kr_matrix.parquet
    matrices/kr_matrix_manifest.json
    matrices/btc_matrix.parquet
    matrices/btc_matrix_manifest.json
    matrices/feature_matrix_run_status.json

Manifests contain input snapshot SHA-256 values and a lineage SHA-256.

## 8. Training split

Random split is not used.

    60% train
    20% validation
    20% test

Each boundary purges the target horizon so a target window cannot overlap the
next evaluation block.

## 9. Feature selection

Selection uses train data only.

Default rules:

    train coverage >= 80%
    non-constant feature
    maximum selected features = 96

Within the train block, absolute correlation to the target is used only to
cap the feature count. Validation and test data are not used for selection.

## 10. Candidate model

V2_001 baseline:

    LogisticRegression
    L2 penalty
    class_weight=balanced
    StandardScaler
    median imputation

Candidate C values:

    0.01
    0.1
    1.0

Selection prioritizes validation ROC-AUC with Brier score as a secondary
criterion.

## 11. Probability threshold

Validation compares:

    0.50
    0.55
    0.60
    0.65

Balanced accuracy chooses the threshold. Test data is not used to choose it.

## 12. Test diagnostics

Stored diagnostics include ROC-AUC, Brier score, log loss, accuracy, balanced
accuracy, precision, recall, selection rate, selected forward-return mean,
median, and win rate.

Forward-return values are research diagnostics, not transaction-cost PnL.
Actual strategy PnL belongs in the vectorbt/walk-forward layer.

## 13. JSON artifact

Each market writes:

    models/us/model.json
    models/us/model_manifest.json
    models/us/test_predictions.parquet

and equivalent KR/BTC paths.

model.json contains no pickle binary. It stores selected features, imputer
medians, scaler parameters, coefficients, intercept, threshold, training
window, metrics, lineage, and sklearn version.

## 14. Manual research run

First refresh Market Tools V2:

    sudo /opt/kalman/app/scripts/run_market_tools_v2.sh

Then train manually:

    sudo /opt/kalman/app/scripts/run_model_v2_research.sh

This performs matrix build, candidate training, JSON export, and an initial
SHADOW score. It is not a cron retraining job.

## 15. Fixed-model SHADOW

To use the existing model without retraining:

    sudo /opt/kalman/app/scripts/run_shadow_v2.sh

This performs latest matrix rebuild and existing model.json scoring only.

It does not retrain, call Toss, or promote a strategy. The base run remains file-only; Neon mirroring is a separate guarded wrapper.

## 16. SHADOW output

    Market_Model_V2/shadow/latest/us.json
    Market_Model_V2/shadow/latest/kr.json
    Market_Model_V2/shadow/latest/btc.json
    Market_Model_V2/shadow/latest/shadow_signals.json
    Market_Model_V2/shadow/history/YYYY-MM-DD/*.json
    Market_Model_V2/shadow/shadow_run_status.json

## 17. SHADOW safety contract

The output shape anticipates a future strategy_signal mapping but remains
file-only.

Required safety values:

    signal = SHADOW
    entry_allowed = false
    payload.allow_trade_shadow = false
    payload.live_execution = false
    payload.production_promotion = false
    payload.neon_write = false

shadow_entry_this_signal may be true as a research observation. It is not an
execution permission.

## 18. Auto-trade boundary

The existing SHADOW_CANARY policy additionally requires
payload.allow_trade_shadow=true plus explicit AUTO_TRADE_SHADOW_CONFIRM.

V2_001 hard-codes allow_trade_shadow=false. The optional Neon mirror preserves that value, writes no dashboard_snapshot, and records pipeline_run as ABORTED so v_latest_successful_run is unchanged. Therefore the V2 mirror is not visible to the current auto-trade join.

## 19. Data-quality gate

Default:

    KALMAN_MODEL_V2_MAX_MISSING_FEATURE_RATIO=0.15

If selected-feature missingness exceeds this threshold:

    risk_gate = DATA_QUALITY_FAIL
    shadow_entry_this_signal = false

## 20. Forward SHADOW

Payload field is_forward_shadow records whether the scoring date is later than
the model refit-through date. This separates in-sample/historical scoring from
genuine forward observations.

## 21. Cron policy

Only a disabled template exists:

    config/model-v2-shadow.cron.example

Retraining is never scheduled by this change. If later approved, only the
fixed-model run_shadow_v2.sh should be considered first.

## 22. Server validation order

    sudo /opt/kalman/app/scripts/preflight.sh
    sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines

    sudo /opt/kalman/app/scripts/run_market_tools_v2.sh
    sudo /opt/kalman/app/scripts/run_model_v2_research.sh

    cat /mnt/gdrive/Market_Model_V2/models/us/model_manifest.json
    cat /mnt/gdrive/Market_Model_V2/models/kr/model_manifest.json
    cat /mnt/gdrive/Market_Model_V2/models/btc/model_manifest.json

    sudo /opt/kalman/app/scripts/run_shadow_v2.sh
    cat /mnt/gdrive/Market_Model_V2/shadow/latest/shadow_signals.json

    sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines

## 23. Promotion gate

Do not promote the Neon mirror beyond research-only storage before all of the following are reviewed:

- actual server provider smoke
- matrix lineage
- cross-market lag policy
- test metrics
- transaction-cost vectorbt backtest
- walk-forward results
- a meaningful period of forward SHADOW observations
- comparison against the existing Unified lineage
- false-positive and drawdown behavior

The progression remains:

    FILE SHADOW
      -> reviewed Neon SHADOW
      -> longer forward observation
      -> optional canary governance
      -> separate live approval

## 24. V2_002 candidates

Future additions may include accumulated Finviz point-in-time history,
authorized Seeking Alpha features, FRED macro data, ECOS KR 3Y/10Y yields,
regime features, calibration, and non-linear candidate models.

V2_001 is intentionally a reproducible leakage-controlled baseline.


## 25. Optional Neon SHADOW mirror

The production Neon schema was verified against project `investment-hub-data`,
database `investment_hub`, branch `production`.

The existing schema is sufficient; no new table or migration is required.

The mirror uses:

    model_registry
      role = SHADOW

    pipeline_run
      status = ABORTED
      metadata.research_status = SUCCESS
      metadata.operational_commit = ABORTED_SHADOW_ONLY

    model_output
      score/probability = probability_up

    strategy_signal
      signal = SHADOW
      entry_allowed = false
      payload.allow_trade_shadow = false
      payload.live_execution = false

It intentionally does not write:

    dashboard_snapshot
    strategy_ledger

This matters because v_latest_successful_run selects only pipeline_run rows with
status=SUCCESS, and auto_trade joins strategy_signal to a READY dashboard_snapshot.
The V2 mirror therefore remains outside both production surfaces.

BTC model records map to the existing database market enum:

    BTC -> CRYPTO

### Enablement

Defaults:

    KALMAN_MODEL_V2_NEON_ENABLED=false
    KALMAN_MODEL_V2_NEON_CONFIRM=

To intentionally enable the mirror on the server:

    KALMAN_MODEL_V2_NEON_ENABLED=true
    KALMAN_MODEL_V2_NEON_CONFIRM=CONFIRM_NEON_SHADOW_MIRROR

Then run:

    sudo /opt/kalman/app/scripts/run_neon_shadow_v2.sh

The wrapper first regenerates the canonical file SHADOW, then validates model
artifact SHA-256 values and safety flags, and only then opens a Neon transaction.

Status is saved to:

    /mnt/gdrive/Market_Model_V2/shadow/neon_mirror_status.json

The writer fails closed when:

- any V2 signal allows SHADOW trading
- live_execution or production_promotion is true
- artifact SHA does not match the file signal
- a model version already exists with a different artifact SHA
- a run_id collides with a different pipeline/model
- any matching dashboard_snapshot already exists

Immediately before commit, the same database transaction re-checks:

- v_latest_successful_run is byte-for-byte equivalent for affected markets
- zero dashboard_snapshot rows exist for V2 run_ids
- zero V2 rows can satisfy the strategy_signal -> dashboard_snapshot auto-trade join
- every V2 pipeline_run remains ABORTED
- every mirrored strategy_signal remains SHADOW with all trade flags false

Any invariant failure raises before commit, causing the transaction to roll back.

This is a research evidence mirror, not production promotion.
