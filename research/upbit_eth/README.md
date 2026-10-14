# Upbit KRW-ETH 1m Backtest (2024–2026)

Isolated research project. Does not modify Kalman LIVE.

## Distribution
- Google Drive ZIP: https://drive.google.com/file/d/1VWCsF-EKdh3wrphkqrE9nhu_6uIHbM1c/view?usp=drivesdk
- Archive: upbit_eth_backtest_v3.zip
- Stored in Drive model_tests.

## Install on Linux server

```bash
mkdir -p ~/research/upbit_eth
cd ~/research/upbit_eth
python3 -m pip install --user gdown
python3 -m gdown 'https://drive.google.com/uc?id=1VWCsF-EKdh3wrphkqrE9nhu_6uIHbM1c' -O upbit_eth_backtest_v3.zip
unzip -o upbit_eth_backtest_v3.zip
cd upbit_eth_backtest_v3
python3 resume_collect.py --db krw_eth_1m.sqlite3 --pages 0
```

After verifying the data is complete, run the grid sweep:

```bash
python3 grid_sweep.py --db krw_eth_1m.sqlite3 --out results_v2
```

Do not use `--allow-incomplete` for final performance reports. Upbit does not generate candles for minutes without trades. No returns are validated until historical collection/audit and backtest have completed.

## Safety
No live orders, no secrets, and no changes to /opt/kalman. The ZIP is the v3 snapshot; source migration into git remains a separate task.
