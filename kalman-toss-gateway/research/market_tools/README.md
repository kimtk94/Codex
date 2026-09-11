# Kalman Market Tools V2 Research

This directory is deliberately isolated from the Toss production runtime.

## Environment

Production:

```text
/opt/kalman/.venv
```

Market collection + Finviz + TA-Lib:

```text
/opt/kalman/.venv-market-v2
```

vectorbt research:

```text
/opt/kalman/.venv-research-v2
```

Never install vectorbt 1.1.0 into the production or Market V2 environments. The current vectorbt release requires pandas 3 and newer NumPy, while the Market V2 collector intentionally remains on pandas 2.x.

## Reproducibility rule

Research scripts do not download fresh price data. They consume saved Kalman snapshots.

```text
Market_Data/v2
  + Market_Features/v2
      -> build_dataset.py
      -> fixed research parquet
      -> run_vectorbt.py
      -> walk_forward.py
```

## Default smoke strategy

`configs/rsi_threshold_v1.json` is a research harness, not an approved Kalman strategy.

It exists to validate the research pipeline and transaction-cost handling.

## Commands

From the deployed app:

```bash
sudo /opt/kalman/app/scripts/install_market_research_v2.sh

sudo /opt/kalman/app/scripts/run_research_v2.sh SPY
sudo /opt/kalman/app/scripts/run_research_v2.sh BTC-USD
sudo /opt/kalman/app/scripts/run_research_v2.sh KOSPI
```

Reports are written under:

```text
$KALMAN_DATA_ROOT/Market_Research/v2/
```

No file in this directory writes to Neon or calls Toss.
