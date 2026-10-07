# Kalman Macro Confirmation V2

Status: research / shadow only. No production trade gate is changed.

## Objective

Connect scheduled US macro releases through one auditable chain:

```text
consensus expectation
  -> official release time
  -> actual - consensus surprise
  -> rate / policy confirmation
  -> equity reaction confirmation
```

This extension does not promote a new executable signal.

## Structured surprise

Trading Economics remains the structured calendar provider for:

- actual
- consensus / forecast
- previous
- provider timestamps

Official BLS / BEA / Federal Reserve sources remain separate provenance anchors.

The reaction timestamp now uses the scheduled `release_at`, not the provider's later `available_at`. The provider availability timestamp is still retained to enforce point-in-time availability.

## PCE support

`CORE_PCE_MOM` and `CORE_PCE_YOY` are now grouped into the `PCE` event family.

The initial PCE shadow score uses the existing generic surprise-event weights:

- normalized surprise: 0.50
- US 2Y confirmation: 0.30
- policy repricing confirmation: 0.20

These weights are engineering priors, not estimated causal coefficients.

The US target impact prior for PCE is 0.65, consistent with its existing MEDIUM indicator tier. PCE remains shadow-only.

## US 2Y limitation

FRED `DGS2` is a daily series. The U.S. Treasury official par-yield curve is also based on daily indicative quotations collected around 3:30 PM ET.

Therefore Kalman must not describe DGS2 as an intraday post-release Treasury reaction.

Current payload semantics:

- `us2y_reaction_quality = DAILY_PROXY`
- component status: `READY_DAILY_PROXY` when the event-day observation exists
- `intraday_confirmation = UNAVAILABLE_NOT_CONFIGURED`

A true intraday 2Y source remains a promotion blocker.

## Equity confirmation

A separate optional shadow layer reads local hourly market bars after the macro release.

Current symbols:

- QQQ: required, Alpaca IEX 1h canonical file
- SOXX: optional; currently unavailable and never replaced with a fabricated proxy

Rules:

- first bar timestamp must be greater than or equal to the actual release timestamp
- maximum entry lag: 90 minutes
- reaction horizons: 1, 4 and 7 hourly bars
- entry price: first eligible bar open
- horizon price: corresponding bar close
- positive inflation / tightening surprise expects negative equity return
- `signed_confirmation_return = -sign(surprise) * equity_return`

Quality label:

`REGULAR_SESSION_1H_POST_EVENT_PROXY`

This is not a high-frequency announcement reaction because premarket and sub-hour moves can be missed.

## Real-file audit

Using the current QQQ canonical 1h file and the September 30, 2026 Personal Income and Outlays release timestamp of 08:30 ET:

- first eligible QQQ bar: 09:00 ET
- entry lag: 30 minutes
- SOXX: `UNAVAILABLE_OPTIONAL`

This confirms the implementation never selects a bar before the release.

## Safety

The extension is explicitly:

- shadow-only
- no order submission
- no R5.x mutation
- no strategy-selection mutation
- no live-trading gate mutation

Promotion requires historical point-in-time consensus data, a true intraday rate source, leakage tests, and walk-forward/OOS validation.
