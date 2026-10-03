# R5.1 Top-K Portfolio Backtest V1

Research-only comparison of portfolio breadth while keeping the R5.1 decision timing and exit contract fixed.

## Strategies

- TOP1: 100%
- TOP2_EQUAL: 50 / 50
- TOP3_EQUAL: 1/3 / 1/3 / 1/3
- TOP3_50_30_20: 50 / 30 / 20
- TOP3_SCORE_PROP: positive Top3 scores normalized to 100%; falls back to equal Top3 when all three are non-positive
- TOP4_EQUAL: 25 / 25 / 25 / 25

## Fixed experimental contract

- Admission timestamps come from the existing R5.1 trade-entry ledger. The Top-K experiment does not create extra entry opportunities.
- Entry universe/ranking comes from a full candidate score table supplied with `--rankings`.
- Exit is FIXED_4: `expected_seq + 4`.
- Friday-flat overrides FIXED_4 only when FIXED_4 would cross the weekend. The position exits on the final available Friday canonical sequence before the Monday-or-later fixed exit.
- Round-trip cost defaults to 10 bps for every fully invested portfolio.
- Primary comparison uses only admissions where ranks 1-4 all have complete entry/exit prices. This enforces a common sample across every portfolio.
- LIVE trading code and the frozen prospective R5.1 benchmark are not modified.

## First server step: locate the full ranking artifact

```bash
cd ~/Codex

git fetch origin research/r5-1-topk-portfolio-20261002
git checkout research/r5-1-topk-portfolio-20261002

bash kalman-toss-gateway/scripts/run_r5_topk_portfolio_backtest.sh   --discover-only
```

The discovery output lists parquet files with a usable sequence, symbol and score schema.

## Run the experiment

```bash
bash kalman-toss-gateway/scripts/run_r5_topk_portfolio_backtest.sh   --rankings /mnt/gdrive/US_ETF/model_lab_v1/results/<FULL_RANKING_FILE>.parquet   --cost-bps 10
```

Optional historical window:

```bash
bash kalman-toss-gateway/scripts/run_r5_topk_portfolio_backtest.sh   --rankings /mnt/gdrive/US_ETF/model_lab_v1/results/<FULL_RANKING_FILE>.parquet   --start 2023-01-01   --end 2025-12-31   --cost-bps 10
```

## Outputs

Default directory:

`/mnt/gdrive/US_ETF/model_lab_v1/results/r5_1_topk_portfolio_v1`

Files:

- `status.json`
- `r5_topk_portfolio_summary.csv`
- `r5_topk_common_trade_panel.parquet`
- `r5_topk_portfolio_trade_detail.parquet`
- `r5_topk_rank_diagnostics.csv`
- `r5_topk_rank_return_correlation.csv`
- `r5_topk_rejected_admissions.csv`

The summary includes total return, CAGR, max drawdown, CAGR / |MDD|, annualized trade Sharpe/Sortino, win rate and trade-return statistics. Rank diagnostics quantify decay from rank 1 through rank 4 and simultaneous-loss behavior.
