# Kalman Grid V3.0 — Upbit KRW 1-minute dataset extension, 2026-10-13 KST

## Verified collection
Source is Upbit public KRW market candles, 1m, with naive timestamps interpreted explicitly as UTC.
- Original fixed dataset Oct 9 00:00 UTC to Oct 12 02:59 UTC: BTC 4,500, ETH 4,483.
- New non-overlap Oct 1 00:00 UTC to Oct 8 23:59 UTC: BTC 11,519/11,520 expected (99.991%, 1 missing minute), ETH 11,502/11,520 (99.844%, 18 missing minutes).
- New data: `/home/taehoon/kalman-data/upbit_grid_research/monthly_1m_20261001_09/`.
- Combined observation counts: BTC 16,019; ETH 15,985. Both sources form an 11-day-and-3-hour window (Oct 1 00:00 UTC – Oct 12 02:59 UTC).
- Most recent data are still missing 1-minute candles possibly because zero trades were made within these minutes. Verify via trades before claiming error.

## Exploratory 1m close-only grid comparison (cumulative 11-day results)
Settings: cash 30,000 KRW, single order 10,000 KRW, 100 candidate levels, assumed 0.05% fee one way, no slippage, no exchange tick rounding; no intrabar fills. 700 recenter observations means 700 *observed* 1-minute candles, not precisely 700 wall-clock minutes.

|Market|Gap|Static return|Static MDD|Rolling 700 return|Rolling 700 MDD|
|---|---:|---:|---:|---:|---:|
|BTC|0.14%|+0.102%|1.497%|-0.944%|3.395%|
|BTC|0.50%|+1.333%|1.384%|-0.325%|2.254%|
|BTC|1.00%|+0.900%|0.860%|-0.182%|1.126%|
|ETH|0.14%|-5.230%|8.873%|-6.709%|10.276%|
|ETH|0.50%|-3.226%|5.640%|-3.311%|6.106%|
|ETH|1.00%|-2.885%|5.184%|-2.773%|6.565%|

**Interpretation:** BTC static at 0.50% has strongest (positive) in-sample return among these six BTC options; ETH remains loss-making in every examined configuration. Rolling 700 not superior for this period. This is a tiny, in-sample, no-slippage, no orderbook study, not evidence of annual net 10% performance. No LIVE, no buy/sell orders.

## Next
- Expand data by month, paginated <=200/request, rate cap <=10/s. Keep UTC-aware metadata and strict continuity audits.
- Introduce Upbit KRW tick table, maker/taker fee tiers, minimum notional and order constraints into simulation.
- Compare actual 1m OHLC path sensitivity, queue/partial fill uncertainty, plus regime baseline and buy-and-hold, cash.
- Walk-forward validation (2020+, separated train/validation/test), report monthly P&L, net return, MDD and exposure. Don't deploy.
