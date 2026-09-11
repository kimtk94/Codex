# Kalman Market Tools V2 Integration Plan

## Purpose

This document maps candidate open-source market-data, screening, indicator, and backtesting tools onto the current Kalman server architecture without changing the frozen production model lineage or Toss execution path.

The current production boundary is:

```text
cron
  -> engine/unified_runner.py
  -> frozen Unified US/KR/CRYPTO model lineage
  -> Neon PostgreSQL
  -> dashboard_snapshot / strategy_signal
  -> engine.position_manager
  -> engine.auto_trade
  -> Toss Open API
```

The existing Seeking Alpha worker is intentionally separate:

```text
authorized SA source
  -> engine.sa_collector
  -> engine.sa_us_btc_features
  -> /Market_Features/sa_us_btc
```

Market Tools V2 should remain shadow/research-only until parity, point-in-time, and backtest validation are complete.

---

## Current overlap found in the repository

### Already in use

- `yfinance==1.7.0`
  - Used directly by `engine/sa_us_btc_features.py`.
  - Provides the current US/BTC/Common daily market download path.
- `pykrx>=1.2.8`
  - Already installed in the server runtime.
  - Appropriate for KRX-specific data and authenticated KRX access.
- FRED API
  - Existing environment variable: `FRED_API_KEY`.
- ECOS API
  - Existing environment variable: `ECOS_API_KEY`.
- Alpaca API
  - Existing Unified lineage compatibility keys are preserved in `engine/pipeline_entry.py`.
- Custom feature calculations
  - RSI, rolling z-score, moving-average gaps, breadth, ratio/regime features, forward targets, and composites are already implemented in `engine/sa_us_btc_features.py`.
- Frozen sklearn artifacts
  - Runtime is pinned to `scikit-learn==1.6.1`.
  - Existing feature definitions must not be silently replaced.

### Production safety already present

- Model pipeline and execution gateway are separated.
- Live trading requires explicit gates.
- Toss order submission has local idempotency and reconciliation.
- Existing SA automation is disabled by default.
- Google Drive writes are mount-guarded.
- Production pipeline uses a lock.
- Current Unified runtime verifies the compressed payload SHA-256 before execution.

These properties should be preserved.

---

## Tool decision matrix

| Tool | Decision | Role in Kalman | Do not use it for |
|---|---|---|---|
| yfinance | KEEP | Primary existing US/BTC market-price adapter and quick market metadata | Sole long-term source of truth for every asset class |
| pykrx | KEEP | KRX-specific price/listing/market-cap data | US/BTC data |
| FinanceDataReader | ADOPT | Secondary provider adapter for KR/US indices, FX, BTC, FRED-style series and cross-checks | Silent replacement of existing production source definitions |
| TA-Lib | ADOPT FOR V2 | Versioned technical-indicator feature namespace | Recomputing frozen production features in place |
| finvizfinance | ADOPT FOR SCREENING | US candidate discovery, descriptive/fundamental/technical screening, news/insider auxiliary snapshots | Historical model training unless daily point-in-time snapshots are archived |
| vectorbt | ADOPT FOR RESEARCH | Strategy validation, parameter sweeps, walk-forward and portfolio backtests | Production trading runtime dependency |
| OpenBB | DEFER / SEPARATE SERVICE | Future provider abstraction, REST/MCP/AI data layer | Direct dependency inside the Toss gateway venv |
| Freqtrade | DEFER | Future exchange-native crypto execution research | Current Toss/US execution path |
| pandas-ta variants | SKIP FOR NOW | Redundant if TA-Lib V2 is adopted | Additional overlapping indicator surface |
| backtrader | SKIP FOR NOW | Redundant with vectorbt for current research objective | Duplicate backtest engine |

---

## Key compatibility rule

Do not replace the current RSI, rolling, breadth, composite, or other feature calculations used by frozen R4/R5.1 artifacts.

Even when two formulas have the same indicator name, implementation details can differ:

- initialization
- missing-value handling
- Wilder smoothing
- lookback warm-up
- calendar-day versus trading-day alignment
- adjusted versus unadjusted prices
- forward filling
- exchange holidays

A numerically small difference can change a trained model's inference.

Therefore new indicators must use a new explicit namespace, for example:

```text
legacy_rsi14
talib_v2_rsi14
talib_v2_macd
talib_v2_adx14
talib_v2_atr14
talib_v2_bbands_pctb
```

Promotion into a production model requires a new model/version, never an in-place substitution.

---

## Proposed architecture

```text
                           KALMAN MARKET DATA V2

      +----------------+    +--------------------+    +----------------+
      | yfinance       |    | FinanceDataReader  |    | pykrx          |
      +--------+-------+    +---------+----------+    +--------+-------+
               |                      |                        |
               +----------------------+------------------------+
                                      |
                              provider adapters
                                      |
                           canonical market schema
                                      |
             +------------------------+-------------------------+
             |                        |                         |
        price/history            macro/common             universe data
             |                        |                         |
             |                        |                +--------+--------+
             |                        |                | finvizfinance   |
             |                        |                +--------+--------+
             |                        |                         |
             +------------------------+-------------------------+
                                      |
                          point-in-time raw snapshots
                                      |
                          feature registry / builder
                         /                         \
                legacy-compatible             talib_v2
                frozen features               new features
                         \                         /
                          +-----------+-----------+
                                      |
                            versioned feature set
                                      |
                       shadow model / research dataset
                                      |
                                  vectorbt
                         walk-forward / cost model
                                      |
                             promotion decision
                                      |
                 new versioned Kalman model artifact
                                      |
                              Neon strategy_signal
                                      |
                       existing guarded Toss execution
```

The execution path must remain unchanged until a separately versioned model is promoted.

---

## Data-layer design

### 1. Provider adapters

Recommended package layout:

```text
engine/
  market_data/
    __init__.py
    schema.py
    yfinance_provider.py
    fdr_provider.py
    pykrx_provider.py
    validation.py
```

Every provider should emit the same canonical columns where applicable:

```text
timestamp
market
symbol
open
high
low
close
adj_close
volume
currency
source
retrieved_at
source_asof
is_adjusted
```

Macro series should use:

```text
timestamp
series_id
value
source
retrieved_at
source_asof
frequency
```

### 2. Source provenance

Never merge providers without recording provenance.

Every saved dataset should contain:

- provider name
- retrieval timestamp
- source observation date
- requested symbol/series
- adjusted/unadjusted policy
- raw row count
- missing-row count
- first/last observation
- checksum when practical

### 3. Cross-provider validation

FinanceDataReader should initially be used as a validation/fallback adapter, not as an automatic replacement.

Example checks:

- SPY/yfinance versus equivalent index/ETF source
- USD/KRW current path versus FDR/FRED
- KOSPI/pykrx versus FDR
- BTC-USD/yfinance versus FDR or exchange archive

Large disagreement should fail the V2 shadow job or mark the feature snapshot degraded.

---

## Screening design

### finvizfinance

Use only for US candidate discovery at first.

Suggested output:

```text
Market_Screeners/finviz/YYYY-MM-DD/
  raw_snapshot.csv
  candidate_universe.csv
  metadata.json
```

Candidate fields can include:

- market cap
- sector / industry
- valuation
- sales/EPS growth
- profitability
- relative volume
- RSI
- SMA20/50/200 relationships
- analyst-related descriptive fields
- insider activity
- news metadata

### Point-in-time rule

Do not backfill today's Finviz snapshot into historical dates.

If a Finviz field is ever used by a model, archive a snapshot every day and only join observations that were available at the relevant model timestamp.

This is required to prevent look-ahead bias.

---

## Indicator design

### Existing legacy calculations

Keep as-is for frozen models:

- RSI implementation in `engine/sa_us_btc_features.py`
- moving-average gaps
- rolling volatility
- z-score
- breadth
- SPY/QQQ/HYG/LQD/BTC ratios
- SA composites

### TA-Lib V2

Add new features only under an explicit versioned namespace.

Initial set:

```text
talib_v2_rsi14
talib_v2_macd
talib_v2_macd_signal
talib_v2_macd_hist
talib_v2_adx14
talib_v2_atr14
talib_v2_natr14
talib_v2_bb_upper
talib_v2_bb_mid
talib_v2_bb_lower
talib_v2_bb_pctb
talib_v2_roc10
talib_v2_obv
```

Do not automatically add all 150+ indicators. Start with a small, interpretable set and remove highly collinear features after validation.

---

## Backtesting design

### vectorbt

Keep vectorbt outside the production Toss gateway environment.

Recommended layout:

```text
research/
  market_tools/
    README.md
    requirements.txt
    build_dataset.py
    run_vectorbt.py
    configs/
    reports/
```

Backtests should consume versioned snapshots exported by Kalman, not refetch fresh internet data during every test.

Required validation:

1. point-in-time feature alignment
2. train/validation/test split by time
3. walk-forward evaluation
4. no forward-filled future information
5. realistic entry delay
6. commission assumptions
7. spread/slippage assumptions
8. US market calendar handling
9. BTC 24/7 calendar handling
10. survivorship-bias review for screened universes

Core outputs:

- CAGR
- annualized volatility
- Sharpe
- Sortino
- maximum drawdown
- hit rate
- turnover
- exposure
- profit factor
- average trade
- worst trade
- rolling performance
- performance by market regime

---

## OpenBB placement

OpenBB is useful, but it should not be installed directly into the current production venv yet.

Reasons:

- current runtime contains pinned sklearn artifacts;
- OpenBB has a broad dependency surface;
- the Toss gateway should stay small and deterministic;
- current data sources already cover the immediate model path.

Future placement:

```text
OpenBB Data Service
   -> REST / MCP
   -> Kalman research/data ingestion
   -> canonical snapshots
```

This can later become the AI-facing market-research layer without coupling it to order execution.

---

## Dependency isolation

Keep the current production file:

```text
kalman-toss-gateway/requirements.txt
```

minimal and execution-safe.

Do not add vectorbt/OpenBB/finvizfinance to it during Phase 1.

Use a separate research environment for experimental tools.

This avoids:

- breaking the frozen sklearn environment;
- increasing gateway startup complexity;
- unplanned transitive dependency upgrades;
- making live trading depend on scraping/research packages.

---

## Implementation phases

### Phase 0 - architecture lock

Status: proposed in this document.

- Keep current production behavior unchanged.
- Keep all new outputs shadow-only.
- Define canonical data schema.
- Define feature-version naming rules.

### Phase 1 - provider adapters

Add:

- FinanceDataReader adapter
- explicit yfinance adapter
- explicit pykrx adapter
- provider comparison checks

Output only to a V2 shadow data directory.

No Neon strategy signal changes.

### Phase 2 - screener snapshots

Add finvizfinance daily candidate snapshot job.

- archive raw snapshot
- generate candidate universe
- store point-in-time metadata
- never permit direct execution from screener result

### Phase 3 - TA-Lib V2 features

Add limited versioned indicator set.

- shadow dataset only
- compare overlapping RSI with legacy RSI
- quantify numerical differences
- preserve current model columns

### Phase 4 - vectorbt validation

Build reproducible research environment.

- consume saved Kalman snapshots
- compare current model against V2 candidates
- include transaction-cost sensitivity
- include walk-forward tests

### Phase 5 - model promotion

Only after validation:

- train a new explicitly versioned model
- write separate strategy version
- run SHADOW
- run canary if approved
- never overwrite frozen artifact lineage

### Phase 6 - OpenBB service

Optional later step.

Deploy OpenBB as an independent data/MCP service and connect it to Kalman research workflows.

---

## Keep / replace / remove summary

### KEEP

- current `engine.unified_runner.py` production lineage
- `engine.pipeline_entry.py`
- Toss execution code
- Neon signal contract
- yfinance current adapter behavior
- pykrx
- current SA collector and SA feature outputs
- current manual legacy feature formulas
- current live-trading safety gates

### ADD

- canonical provider interface
- FinanceDataReader provider
- cross-provider validation
- finviz point-in-time screener snapshots
- TA-Lib V2 namespace
- vectorbt research environment
- feature schema/version metadata

### DEFER

- OpenBB in a separate service
- Freqtrade for exchange-native BTC trading

### DO NOT REPLACE IN PLACE

- frozen model inputs
- current RSI/composite formula definitions
- strategy signal schema
- Toss execution lifecycle

---

## Additional repository observations

### 1. Encoded Unified payload

The SHA-256 guard in `engine/unified_runner.py` is a strong integrity control, but the split LZMA+base64 payload makes normal code review and diffs difficult.

For the next-generation model, prefer:

```text
plain versioned source
+ immutable model artifact
+ manifest
+ SHA-256
```

rather than adding more encoded source chunks.

Do not rewrite the current frozen lineage merely for cleanup.

### 2. Public repository scope

The repository is public and also contains non-Kalman business documents and price/manual files at the repository root.

Consider separating:

- Kalman source code
- private/company operational documents

into different repositories or moving sensitive operational material to a private repository.

No credentials should ever be committed; the current `.env.example` correctly leaves secrets blank.

---

## Promotion checklist

A Market Tools V2 model may move toward production only when all are true:

- [ ] provider provenance recorded
- [ ] point-in-time rules verified
- [ ] legacy versus V2 indicator differences measured
- [ ] no look-ahead leakage
- [ ] survivorship bias reviewed
- [ ] vectorbt walk-forward complete
- [ ] transaction-cost sensitivity complete
- [ ] feature schema frozen
- [ ] model artifact versioned
- [ ] SHADOW results acceptable
- [ ] Toss path unchanged
- [ ] live gates remain fail-closed

