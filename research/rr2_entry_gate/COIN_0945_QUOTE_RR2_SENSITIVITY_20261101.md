# COIN B 09:45 SIP Quote Age × Net RR2 Ex-Ante Reprice Gate (2026-11-01)

**Research only — LIVE HOLD.** Frozen original model 126 reconstructed signals (2025 80, 2026 46). The `PRIOR_LOW_BUFFER_2R` 4-session retrospective trade candidates had **2025 17, 2026 7** modeled entries. Their quote entry is a proxy, **not** a fill.

## Primary evidence and reproducibility

- [Official historical SIP pilot run #41255467419](https://github.com/kimtk94/Codex/actions/runs/41255467419): 24 matched trade windows, original 1,000ms freshness.
- [Pre-entry quote age sensitivity run #41259049757](https://github.com/kimtk94/Codex/actions/runs/41259049757): 500, 1000, 2000, 5000ms; timestamps **strictly before** 09:45; equal timestamps excluded; all closed historical SIP.
- **[Historical quote-ask RR2 reprice run #41259307604](https://github.com/kimtk94/Codex/actions/runs/41259307604) — SUCCESS**, archive `kalman-coin-pinned-original-pit-reconstruction`.
- Reconstructed source commit `cccbb80059ab626da0cbd76cd825f879870f6727`, 221,014 bars across 5 original symbols, 711 complete COIN NYSE sessions, signal count parity 20/20 and EOD parity 10/10. The 2025/26 data are repeatedly viewed, never unseen OOS.
- All provider quote/15m row data and exact signal dates are private and only aggregate counts are published.
- Source quotes are unadjusted raw SIP while 15m bars use corporate-action `adjustment=all`. We rejected source comparisons when quote midpoint differed by >2% from bar-open; no such outliers occurred in this small pilot. This tolerance is an **exploratory** QC threshold, not a proof of instrument adjustment consistency.

## Historical quote freshness sensitivity (NOT authorization to relax 1s)

| Quote freshness | 2025 valid /17 | 2026 valid /7 | 2025 original target RR2 violations | 2026 original target RR2 violations |
|:--|--:|--:|--:|--:|
| <=500 ms | 13 | 0 | 13/13 | 0/0 |
| **<=1000 ms (primary)** | **16** | **3** | **14/16** | **2/3** |
| <=2000 ms (diagnostic only) | 17 | 4 | 14/17 | 3/4 |
| <=5000 ms (diagnostic only) | 17 | 7 | 14/17 | 6/7 |

The last strictly preceding quote for a trade is used; quotes at exactly 09:45:00 or after are prohibited. Larger quote age never proves availability at 09:45 for a buy order. In 2026, all 7 events have a quote within 5s but **none** within 500ms and only **3** within 1000ms.

## Hypothetical quote-ASK entry + unchanged absolute stop, ex-ante target dynamically re-priced

Retain the original absolute previous-day-low stop (including its buffer). Replace theoretical 15m bar opening price with the strictly earlier SIP ask. At each cost, recompute risk `(ask - stop)/ask` and target `2*risk + 3*roundtrip_cost`; reject stop beyond 0.5%–3% or target >8%. No future prices in the plan. **These 'passes' are only mathematical eligibility — not verified executions**.

| Primary quote age <=1000ms | Quoted ask valid | 30bp geometry pass | 50bp geometry pass | 100bp geometry pass |
|:--|--:|--:|--:|--:|
| 2025 B modeled 17 trades | 16/17 | 14/16 (14/17 original) | 14/16 | 12/16 |
| 2026 B modeled 7 trades | 3/7 | 3/3 (3/7 original) | 3/3 | 2/3 |

2025 primary 30bp rejects 2 because stop width >3% at quoted ask. 2026 primary 100bp rejects 1 because revised target >8%.

At 5-second stale threshold (exploratory only), 2025 math pass: 15/17 at 30/50bp and 13/17 at 100bp; 2026: 7/7 at 30/50bp and 5/7 at 100bp. **Never infer these would be tradable:** stale snapshots are NOT sanctioned order-entry prices.

## Interpretation and required next steps

- **Historical 30bp adjusted-bar close-to-close model B 4-session realized R after conservative gap target cap:** 2025 **-0.328021** (n=17), 2026 **+0.714286** (n=7). These are not quote-adjusted backtest returns and must NOT be presented as though 3/7 quotes establish 3 successful trades.
- A quoted **ask** is only the top-of-book view at a moment prior to 09:45, not an actual broker fill or guaranteed available depth/size. Directly adding the ask premium on top of a modeled 30bp roundtrip **risks counting entry slippage twice**, since baseline already assumes 5bp slippage per side.
- No contemporaneous exit-side quotes/stop market order book or broker execution ledger; target hitting in 15m OHLC is not sufficient to claim a limit fill. Corporate-action-adjusted bars versus raw SIP NBBO can have unresolved price basis.
- **Strict primary 1-second gate is not relaxed.** Even with hypothetically geometrically valid quoted ask, 2026 has only **3 usable entry snapshots in 7 modeled executed trades**. No stable two-year positive R and no untouched forward evaluation.
- Future true OOS starts after 2026-11-01 model/policy freeze. Keep timestamped signals/actual order eligibility private, record all no-trades and overlaps; do not backfill fabricated signals or change thresholds after observing returns. Independent >=30 completed trades are merely a preliminary minimum, not a performance guarantee.

**Decision: LOCK RESEARCH / LIVE HOLD; no existing production/broker configuration changes.**
