# Kalman COIN — prospective research freeze and execution-evidence acceptance gate

**Frozen:** 2026-11-01 KST, following retrospective matched COIN 126-event reconstruction. **Research-only / LIVE HOLD.**

## Source and validation status

- V_unweighted logistic model is the original `cccbb80059ab626da0cbd76cd825f879870f6727` implementation (3 price features + RVOL20 and volume z-score, signal after fully completed NYSE RTH session, probability >=0.50). 2026 fit uses strictly prior years, with purged label boundary.
- 2025/2026 evaluated history has already influenced research and **cannot** be called pristine holdout, regardless of train/test mechanics.
- 2026 B / previous-day-low 4-session arm produced 7 recorded trades and a fragile retrospective positive average. 2025 B was negative. This is **not** a qualifying candidate for automatic LIVE promotion.
- All four geometry arms A/B/C/D and 1/2/4-session exit horizons are retained for **exploratory registered comparison**. No retrospective selection of a winning arm to justify subsequent LIVE entry.
- Stops gross <=3%, targets gross <=8%, planned reward/risk AFTER roundtrip costs >=2.0, no overlapping positions per arm. The target must be repriced **ex ante** at the assumed cost. Never relax these conditions silently.
- Gap-down stop uses the worse open; gap-up take-profit uses **planned limit target**, not the gap-open windfall. Same-bar STOP first. Exits need bid/ask/latency validation; 15m OHLC paths do **not** certify a fill.

## Future genuinely forward data, beginning only after this freeze

1. Produce a hash-stamped signal snapshot after each complete XNYS RTH close. Never include the next session OHLC/quotes in features. Freeze model source SHA, historical training end date, decision threshold, per-signal feature availability, and a reference record of 30/50/100bp target policies before examining subsequent outcomes.
2. Evaluate only the subsequent session's 09:45 execution opportunity. Guard exchange holidays, DST, early close, 15m coverage, quote timestamp ordering, corporate-action adjustment consistency, quote depth unit conventions, and insufficient quote evidence. Any unknown condition must result in **HOLD**, not simulated best-possible fill.
3. Once subsequent sessions have fully closed and the 1/2/4-session horizon has elapsed, calculate returns. Apply consistent right censoring; retain all non-entered eligible signal records, overlap blocks, no-trade decisions, gap loss tails and quote coverage. New outcomes may NOT be used to retune the original policy or change thresholds mid-test.
4. Publish only aggregated counts, model-frozen SHA, source health, monthly returns, R distribution, target-before-stop frequencies, pre/post-cost risk and maximum drawdown. Keep raw SIP tape, exact signal times, quotes, and orders private.
5. At least **30 independent executed, closed trades in the chosen frozen configuration** are a preliminary review floor, *not* proof of profitability. Require multiple calendar regimes, materially positive cost-stressed R with uncertainty, tolerable downside tail/MDD and full execution evidence before considering a new human-reviewed decision. If insufficient signals/trades or no positive evidence, retain HOLD and extend prospective observation without changing policy.

## Quote pilot currently separate from executed fills

- Exact original-model B 4-session: 17 executions in 2025 and 7 in 2026, total 24.
- Fetch historical COIN SIP quote data in five-second pre-entry windows, strictly preceding 09:45 NY. Accept noncrossed positive bid/ask <=1000ms stale; flag raw-versus-adjusted price-scale disagreement, missing quotes, and invalid spreads. Historical quote size units changed; never infer accessible position depth without normalization.
- The latest pre-entry **ask** is a hypothetical marketable-buy proxy, **not** an actual broker fill. Quoted spread and ask-open premium are not necessarily additive to the baseline 30bp (which already includes modeled slippage).
- For target-gap exits, no fill should be claimed from 15m OHLC alone; conservative planned limit target cap remains mandatory until venue-level order and quotes are available.
- If the historical quote provider has no coverage or a substantial source mismatch, the result must remain `QUOTE_SOURCE_HOLD`.

## Promotion decision

Automatic promotion: **never**. The current 2025/2026 exploratory backtests and the quote-only pilot can rule out assumptions, but cannot approve LIVE. Prospective evidence and separate authorized review are required. No current broker, risk, signal, sizing, or LIVE changes.
