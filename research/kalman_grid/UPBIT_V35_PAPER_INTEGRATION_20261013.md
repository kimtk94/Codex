# Kalman Grid V3.5 — Upbit KRW PAPER ledger integration (2026-10-13)

**Implemented in GitHub research branch; execution / profitability not yet verified.**

- `upbit_paper_grid_v35.py`: Upbit-specific subclass of the existing Decimal-ledger RollingGrid. BUY prices round down to Upbit ticks; SELL prices round up. Min KRW 5,000 notional and 10000 KRW intended order size checked. Orders and inventory use the previous paper Ledger. Existing lots and open sells preserved at recenter. Full ledger audit at end of `evaluate_upbit()`. No broker connections.
- `test_upbit_paper_grid_v35.py`: five authored tests (tick/size, buy-sell, recenter, smoke evaluation, slippage guard). **Not executed on server; do not state PASS**.
- `upbit_v35_september_runner.py`: CSV/manifest runner, 2026-09 Upbit BTC and ETH full-month input, gaps 0.14/0.50/1.00%, static and 700-observation rolling = 12 cases.
- Server data prepared and quality-PASS: `/home/taehoon/kalman-data/upbit_grid_research/v32_sep_full/{KRW-BTC,KRW-ETH}_1m_history.csv`.

Research limitations: hypothetical close-triggered limit fills, no slippage (explicitly rejected if requested), no maker/taker queue, no partial fills, no orderbook, no cost sensitivity or OOS selection. Fees default 0.05% each side as an assumption, not verified account-specific fee. Pending clean automated test run and month-sweep execution; **do not invent backtest returns**.

Follow-up from clean research repo (not dirty LIVE checkout):
```bash
cd /home/taehoon/kalman-grid-v30-research
git pull --ff-only origin research/kalman-grid-v25-20261012
cd research/kalman_grid
python3 -m unittest test_upbit_krw_rules_v33 test_upbit_grid_contract_v34 test_upbit_paper_grid_v35 -v
python3 upbit_v35_september_runner.py --input-dir /home/taehoon/kalman-data/upbit_grid_research/v32_sep_full --out-dir /home/taehoon/kalman-data/upbit_grid_research/v35_sep
```
Note: normal execution and simulation require review of edge case invariants on rounded post-buy SELL placement. Never deploy to LIVE without tests plus OOS evidence.
