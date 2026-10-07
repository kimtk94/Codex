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


## Intraday US 2Y provider

Trading Economics exposes the US 2-year Treasury yield as market symbol
`USGG2YR:IND`. The public instrument page metadata was used only for symbol
discovery.

The Trading Economics markets intraday endpoint supports 1-minute through
4-hour bars and historical intraday requests of up to 30 days. Kalman uses the
1-minute REST endpoint for a research-only delayed intraday confirmation layer.

Configuration:

- provider: Trading Economics
- symbol: `USGG2YR:IND`
- interval: 1 minute
- event families: CPI, PCE, NFP, FOMC
- pre-event window: 10 minutes
- reactions: +5m, +15m, +30m, +60m
- primary confirmation horizon: +15m
- collection window: event age 5–120 minutes
- quality: `DELAYED_INTRADAY_RESEARCH`

Leakage rules:

- baseline must be the last timestamp strictly before the release
- the baseline must be no more than 5 minutes stale
- each post-event observation must be at or after its target horizon
- a post-event timestamp gap above 2 minutes blocks that horizon
- a missing or stale baseline blocks the entire reaction
- no DGS2 daily value is substituted for a failed intraday observation

Entitlement handling is fail-closed:

- missing credential -> `UNCONFIGURED_CREDENTIAL`
- demo credential -> `DEMO_CREDENTIALS_REJECTED`
- HTTP 401/402/403/404/410 -> `UNAVAILABLE_PROVIDER_ENTITLEMENT`
- other provider errors remain explicit errors

The provider uses the existing `TRADING_ECONOMICS_API_KEY` environment
variable. It never logs the credential.

### Read-only entitlement probe

After installation on the server:

```bash
sudo /opt/kalman/app/scripts/probe_macro_intraday_us2y_v1.sh
```

The probe loads the existing root-only Kalman environment, requests a short
recent US2Y intraday window, prints only sanitized provider/status data and
never touches trading execution.

### Real-time boundary

This implementation deliberately uses the REST intraday feed and is labelled
delayed/research-only. Trading Economics also documents a live markets
WebSocket, but non-demo market subscriptions require appropriate key/secret
entitlement. Do not promote the REST confirmation to a live trade gate.

If the existing Trading Economics subscription does not include US2Y
intraday, Twelve Data `US2Y` is the first fallback candidate. It exposes the
instrument as `US Treasury Yield 2 Years` and its time-series API supports
1-minute intervals, but account entitlement must be verified separately.


## Keyless public 5-minute US2Y fallback

The public Trading Economics US 2-year note page exposes chart metadata for
`USGG2YR:IND` and lists 5/15/30/60-minute chart resolutions. Its web chart
loads a public CloudFront chart datasource without requiring the account API
credential.

Kalman can use that datasource only as a prospective shadow fallback when the
authenticated Trading Economics API is unconfigured or unavailable.

Provider priority:

1. authenticated Trading Economics 1-minute intraday API
2. Trading Economics public web chart 5-minute datasource
3. block intraday confirmation

The fallback is explicitly labelled:

`PUBLIC_WEB_CHART_5M_SHADOW`

It is not treated as the documented Trading Economics API and is not suitable
for production promotion because the web-chart contract is undocumented and
may change.

The chart payload is the same encoded payload consumed by the public page.
Kalman decodes it using the obfuscation/decompression procedure present in the
public chart JavaScript and extracts only the USGG2YR:IND OHLC series.

Fallback quality gates:

- baseline strictly precedes the macro release
- baseline gap <= 10 minutes
- first observation at/after each reaction horizon
- post-target gap <= 10 minutes
- source range must actually contain the event
- no DGS2 substitution when the public chart is missing or stale

A live no-key probe on 2026-10-08 KST returned 247 recent US2Y observations,
with the public chart provider identified explicitly and trade execution
disabled.
