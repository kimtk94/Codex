# Kalman Grid V3.7 — User-provided server verification (2026-10-13)

Source: server console log provided by user; not independently fetched from host.

## Test run
- Upbit V3.3–V3.5: 13/13 PASS.
- Ledger standalone: 10/10 PASS.
- Discovery suite: 25/25 PASS. Discovery repeats 13 Upbit tests; 35 distinct test cases are supported by logs.
- One non-failing ResourceWarning in test_v24.py about unclosed CSV file.
- Data audit: BTC 43,197 / 43,200 minutes (99.993%, 3 gaps); ETH 43,165 / 43,200 (99.919%, 34 gaps representing 35 missing minutes).
- Period: 2026-09-01 through 2026-09-30 UTC, Upbit KRW 1m.
- Full PAPER v35 September sweep completed: 12 cases.
- Results server path: `/home/taehoon/kalman-data/upbit_grid_research/v37_validation/upbit_v35_sept_sweep.csv`.

## Verified results from console CSV
|market|spacing %|recenter observations|return %|MDD %|fills|fees KRW|final equity KRW|
|---|---:|---:|---:|---:|---:|---:|---:|
|BTC|0.14|0|0.352460|5.602477|52|260.183|30105.738|
|BTC|0.14|700|-0.777766|7.856337|127|635.436|29766.670|
|BTC|0.50|0|1.068471|4.936322|16|80.200|30320.541|
|BTC|0.50|700|2.019107|7.174968|43|215.526|30605.732|
|BTC|1.00|0|3.300474|4.128174|22|110.550|30990.142|
|BTC|1.00|700|0.878650|4.621574|11|55.250|30263.595|
|ETH|0.14|0|2.936987|4.572299|264|1321.101|30881.096|
|ETH|0.14|700|-0.454934|5.088664|183|915.731|29863.520|
|ETH|0.50|0|6.037069|3.925467|86|431.121|31811.121|
|ETH|0.50|700|5.827968|4.396545|93|466.211|31748.391|
|ETH|1.00|0|5.194675|2.919617|34|170.865|31558.402|
|ETH|1.00|700|4.383468|2.716009|33|165.819|31315.040|

Best one-month nominal return: ETH static 0.50%, +6.037% and MDD 3.925%; NOT a validated live or OOS profitability claim. Closely related 0.14% ETH static generated 264 hypothetical fills and incurred 1,321 KRW fees (4.4% of 30,000 initial capital), signifying severe turnover-cost sensitivity. Fees modeled at 0.05% each side; no slippage, partial fills, order book/queue, OOS separation.

## Next
1. Correct V3.5 paper engine failure/exception edge cases before treating it as robust; reproduce full tests from clean repo.
2. Add effective slippage and maker/taker fill stress (e.g. 0.02%,0.05%,0.10% each side), preserving ledger conservation, compare hypothetical net outcomes.
3. More contiguous, non-overlapping months including drawdown regimes; out-of-sample ranking versus hold BTC, hold ETH and cash.
4. Report monthly total return, equity curve, realized/unrealized return, turnover, annualized only over adequate history and actual trading assumptions.
5. Keep LIVE untouched.
