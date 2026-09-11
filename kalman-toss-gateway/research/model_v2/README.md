# Kalman Model V2

Research-only model pipeline built on saved Market Tools V2 snapshots.

## Contract

    Market_Data/v2
       +
    Market_Features/v2
       -> US/KR/BTC feature matrix
       -> purged chronological train/validation/test
       -> regularized logistic candidate
       -> JSON model artifact
       -> file-only SHADOW signal

The model artifact is JSON, not pickle. It contains selected feature names,
imputer medians, scaler means/scales, logistic coefficients/intercept,
probability threshold, metrics, matrix lineage, and sklearn version.

## Safety

Generated SHADOW signals always set:

    signal=SHADOW
    entry_allowed=false
    payload.allow_trade_shadow=false
    payload.live_execution=false
    payload.production_promotion=false
    payload.neon_write=false

This package does not write Neon and does not import the Toss client.

## Research / retraining

    sudo /opt/kalman/app/scripts/run_model_v2_research.sh

This rebuilds matrices, retrains candidates, exports JSON artifacts, and
creates an initial SHADOW score.

## Fixed-model SHADOW

    sudo /opt/kalman/app/scripts/run_shadow_v2.sh

This rebuilds only the feature matrices and scores the existing JSON
artifacts. It does not retrain.

Research/retraining should remain manual until governance rules are approved.
