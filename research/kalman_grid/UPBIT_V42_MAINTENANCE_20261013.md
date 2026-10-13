# Upbit Grid V4.2 — 2026-07-06 exchange maintenance handling

Official Upbit notice: https://docs.upbit.com/kr/v1.6.4/changelog/server_maintenance_0706

Confirmed user-provided CSV gaps for both BTC/ETH:
- last pre-gap candle 2026-07-05T17:00:00Z
- first post-gap candle 2026-07-05T21:51:00Z
- 290 missing one-minute intervals.
- Upbit scheduled KST 2026-07-06 02:00~07:00, staggered restart from 06:40.
- At resume, Upbit cancel condition: BUY price > pre-maintenance last traded price, SELL price < pre-maintenance last traded price. Others generally preserved.

Implemented PAPER ONLY:
- `upbit_maintenance_v42.py`: exact known-gap classification, conditional cancellation and gap report.
- `upbit_maintenance_paper_v42.py`: retains positions, applies cancel policy and blocks hypothetical fills on first post-gap bar while marking equity. No broker calls.
- `upbit_v42_july_gate.py`: adjusted availability-based coverage after subtracting **only** documented 290-minute outage; other gaps remain visible and max ordinary gap <=5 min; requires exact first/last monthly minute and >=99% adjusted coverage.
- `test_upbit_maintenance_v42.py`: regression cases authored, not yet server tested.

Known cautions:
- Official maintenance policy does not imply an order execution immediately when trading resumes; no queue or partial fill model.
- Historical observed candle at 17:00 UTC is the first minute of the scheduled maintenance clock hour, and using its close as actual **pre-maintenance last trade** is unverified. Until 1-minute OHLC/trade-side chronology and precise last trade are confirmed, the cancellation reference is a proxy and should not be treated as exchange-exact.
- Strict matching only to observed 290-min gap for 2026-07-06, not a generic whitelist.
- Maintain both raw audit BLOCKED and adjusted maintenance status in report.
- No live trade/code changes.

Next: syntax/test and quality gate execution; validate correct pre-maintenance trade reference and maint-state sensitivity; July PAPER comparison only after proof.
