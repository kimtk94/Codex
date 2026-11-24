# Target +20% average net return — exploratory expanded sweep

Data: 190 complete still-listed KRW cohorts from GitHub Actions artifact 12555802314, 15m candles. Locally run script: /mnt/data/upbit_regime_engine/target20_audit.py. Research-only.

Sweep: 4 filters (base, liquidity cooling, price structure, all), 3 entry cutoff settings (24/48/168h), 7 profit-targets (+10/+20/+30/+50/+75/+100/+150%), 3 stops (-3/-5/-10%) = 252 combinations per train/test partition. Full trade-level outputs in local CSV. Fee 0.05% and assumed slippage 0.15% each way. No live orders.

For strategies with >=20 trades per partition:
- Best 2023–25 in-sample mean net: +1.6699% (liquidity cooling, 24h, +75% TP, -3% SL), n=89, median -3.2423%, TP rate 5.62%.
- Best 2026 exploratory mean net: -0.1911% (price structure, 24h, +10% TP, -3% SL), n=51.
- No strategy reaches +20% average net in either partition.
- All-filters, deadline 24h, stop -3%: +10% TP = -0.9946% train and -0.5282% 2026; +20% TP = -0.1833% train / -0.5746% 2026; +30% TP = +0.2689% train / -0.9457% 2026; +50% TP = -0.4227% train / -2.0128% 2026; +100% TP = -1.1963% train / -0.8529% 2026.

LIMITATIONS: cutoff checks use observed bar count ×15m, not wall-clock elapsed time; candle gaps can distort exact deadlines. Existing state engine uses historical bars, but historical delisted markets are absent. Stop-first intrabar assumptions, time-based exit and fee/slippage are approximations; no real quote depth or execution data. Multiple hypothesis search contaminates 2026 as holdout; results must not be described as independent out-of-sample. No portfolio MDD yet. No live deployment warranted.
