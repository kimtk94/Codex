# 2026 profit-flip counterfactual — offline research, not LIVE

## Scope and immutability
- No TOSS order API, cron, active trade settings, Neon writes, or production model artifact writes.
- Source: 251 frozen R5.1 model **in-sample** trade ledger records in Neon
  `strategy_ledger`, dated 2026-01-02 through 2026-09-02. These are NOT real executions.
- Source: 16 real closed `PROFIT_TO_LOSS_FLIP` positions (2026-09-22 to
  2026-10-09). Ten had one confirmed initial BUY, four contained add-on buys,
  two were adopted holdings without original BUY telemetry.
- All Neon snapshots and raw market data stay on the server under
  `$KALMAN_FLIP_RESEARCH_ROOT` and MUST NOT be committed or made public.
- Feed: Alpaca historical SIP `5Min` OHLCV (`adjustment=raw`) fetched using the
  user's existing locally stored credentials; the secrets are never echoed.

## Contract
- Freeze the same model-selected trade entry/holding symbols for all exit policies.
- Model 60m timestamps label **bar start**; its timestamp +60m, capped at NY
  16:00, is the earliest known time. Simulated research entry at next
  5-minute bar **close**; an alternative entry-price-anchor mode retains the
  original model reference price while preserving causal monitoring times.
- Do not consult future prices when deciding. Trading takes place only during
  the NY 09:30–16:00 regular session. Use bar CLOSE, not unknown intra-bar
  bid/ask, for an approximate next-watch execution.
- Profit-flip guard: armed after price return >=+0.20%. Exit if two consecutive
  5m observed CLOSE returns are <= threshold. Compare -0.2%, -0.5%,
  -1.0%, -1.5%, -2.0%, and OFF.
- Exit priority: <=-3% STOP, >=+20% TAKE, profit flip if enabled,
  Friday 15:45 NY forced exit, then historical 4 signal bucket cap.
- Actual live **model rotation is unavailable** in a historical same-entry
  replay; code explicitly reports it as unmodeled. Changes to early-exit
  capital redeployment are also unmodeled.
- Fixed cost sensitivities: 10 bps or 25 bps of entry value (total round trip).
- Sequential-trade equity path and drawdown are **proxies**, not actual account
  P&L, since full portfolio sizing, simultaneous positions, FX and broker
  slippage are not modeled.

## Execution, after preserving ledger snapshots
```bash
export KALMAN_FLIP_RESEARCH_ROOT=/home/taehoon/kalman-data/trading/research_flip_2026
export KALMAN_RESEARCH_ENV_FILE=/home/taehoon/Codex/kalman-toss-gateway/.env
PYTHONPATH=kalman-toss-gateway python3 -m unittest discover -s kalman-toss-gateway/tests -p test_flip_exit_replay_2026.py -v
python3 kalman-toss-gateway/research/quant_stack/flip_exit_backfill_2026.py --feed sip --limit-rpm 110
python3 kalman-toss-gateway/research/quant_stack/flip_exit_replay_2026.py --feed sip --cost-bps 10
python3 kalman-toss-gateway/research/quant_stack/flip_exit_replay_2026.py --feed sip --cost-bps 25
python3 kalman-toss-gateway/research/quant_stack/flip_exit_replay_2026.py --feed sip --cost-bps 25 --entry-mode legacy
python3 kalman-toss-gateway/research/quant_stack/flip_exit_replay_2026.py --feed sip --cost-bps 10 --no-friday-flat
python3 kalman-toss-gateway/research/quant_stack/flip_exit_robustness_2026.py
python3 kalman-toss-gateway/research/quant_stack/flip_exit_live_counterfactual_2026.py
```

## Limits and interpretation
- The 251 original R5.1 model signals themselves carry a documented
  **in-sample/not-OOS** warning. Optimizing flip threshold here is research,
  not a validated live strategy.
- Two-entry/three-entry **LIVE** trades use their final (ex-post) weighted cost
  as a price anchor in the 16-position diagnostic and are excluded from its
  strict 10-single-entry cohort to avoid lookahead.
- Live 16 trades were selected **because they were flip exits**; not a fair
  standalone portfolio sample. Replay uses 5m-close observations and does NOT
  perfectly reproduce the TOSS last-price watcher or fills.
- Friday 15:45 ET is a **research assumption**, not a reconstruction of every
  historical TOSS fractional-order cutoff.
- A missing bar, inexact model/source entry price, split, halt or real broker
  fill friction can change threshold crossings.
- Paired day/month bootstraps quantify variation **conditional on frozen
  in-sample entries** and do not correct model fitting, selection or snooping.
- Do **not** change production `AUTO_TRADE_PROFIT_FLIP_*` settings from this
  research without forward prospective shadow confirmation.
