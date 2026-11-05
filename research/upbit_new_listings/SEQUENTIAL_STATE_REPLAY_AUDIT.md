# Sequential 15-minute crash regime engine — initial local replay

Research-only, no live policy change. Input: full 190 complete cohorts from artifact 12555802314 (130,559 original candle rows; incomplete/sparse excluded).

Rule: at each completed 15m candle, detect a price low >=20% below previous completed candles' running high; reset waiting counter when new intrabar low appears; after >=4 completed candles without a new low, require closing price >=3% above trough; enter at NEXT candle opening price. Stop -3% and target +10% with stop-first handling if both touched, assumed fee 0.05% per side and slippage 0.15% per side. Liquidate no later than available first seven days. No pre-crash entry.

| Period | Full cohorts | Crash observations | Entries | Net win % | Mean net % | Stop | Take | Expiry |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023–25 | 120 | 111 | 110 | 11.82 | -1.7098 | 97 | 13 | 0 |
| 2026 explored | 70 | 60 | 60 | 15.00 | -1.4238 | 51 | 8 | 1 |

Three local state tests passed: no crash => no entry; repeated fresh lows => no entry; entry occurs after completed confirmation candle. Local code and output files produced but not yet uploaded to repository; results are local exploratory audit, not CI PASS.

Limitations: data is prior already-inspected samples; delisted markets absent; single trade per market; end of weekly window and gaps use observed bars, not an order book; stop-first same-candle assumption; no BTC alignment, market impact, 15m-to-1m execution audit, or portfolio MDD. No statistically established positive expected return; live trading prohibited.
