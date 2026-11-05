# COIN original-model PIT 126 signals — dynamic cost / block-bootstrap validation (2026-11-01)

**Status: Research-only / LIVE HOLD.** No broker changes, LIVE exits or promotion.

## Reproducible source

- Pinned source commit: `cccbb80059ab626da0cbd76cd825f879870f6727` from original five-symbol research
- Original 5-symbol SIP run: [#41217666574](https://github.com/kimtk94/Codex/actions/runs/41217666574)
- Source reconstruction and result: [#41224457018](https://github.com/kimtk94/Codex/actions/runs/41224457018)
- Independently audited statistics: [#41224981517](https://github.com/kimtk94/Codex/actions/runs/41224981517)
- **Private actual 30 / 50 / 100bp repriced rerun: [#41225376132](https://github.com/kimtk94/Codex/actions/runs/41225376132) SUCCESS**
- Source: 221,014 original five-symbol Alpaca SIP 15-minute records; 711 complete COIN NYSE sessions; **20/20** 5-symbol model/year signal cohorts and **10/10** historical EOD returns match original reports. COIN `V_unweighted` candidate signals: 2025 **80**, 2026 **46**.
- These 126 dates are **recomputed from frozen original-model source**, not found in an original archived per-date signal ledger.

## B / prior-day low stop; 4 exchange-session horizon; dynamic net RR>=2.0

Targets are **recomputed before entry at every assumed cost** (not simply deducting an extra fee from the old 30bp target), subject to gross stop <=3% and gross target <=8%. Same model signal cohort and pessimistic stop-first OHLC barrier convention.

| Roundtrip friction | 2025 trades | 2025 mean realized R | 2026 trades | 2026 mean realized R | 2026 bootstrap 95% mean-R band | 2026 mean R after excluding best single trade |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 30bp | 17 | **-0.264** | 7 | +0.988 | [-0.571, +2.000] | +0.500 |
| 50bp | 17 | **-0.289** | 7 | +0.597 | [-0.571, +2.000] | +0.099 |
| 100bp | 13 | **-0.532** | 7 | +0.488 | [-0.571, +2.000] | +0.083 |

2026 B entry trades span only **4 separate calendar months**. The 95% empirical bands use 4,000 entry-month cluster bootstrap resamples and are **descriptive conditional on this reused history, NOT unseen OOS return confidence guarantees**. A 7-trade sample is fragile. Dropping the best trade reduces 50bp expectancy from +0.597R to +0.099R.

## All strategy cells and hard decision

- Four fixed ex-ante structures × three holding windows × two years × three roundtrip costs: **72 results**; every 30bp result must exactly reproduce the previously stored 24 model-matched annual cells or the job fails.
- For 30, 50 and 100bp, **zero of 12 arm/horizon combinations** had positive mean R in **both 2025 and 2026**. Selecting the best 2026 arm post-hoc is disallowed.
- The original risk geometry is unmodified: stop max 3%, target max 8%, cost-inclusive planned RR≥2 before entry; 09:45 entry with no repeat entries while a position is held.
- The earlier cost-sensitivity calculation held targets fixed; that is distinct from the above **dynamically repriced target** experiment.
- Even for configurations where a cluster-bootstrap lower limit happens to be positive, the dates were already examined and there is no pristine future OOS evidence.

## What remains BEFORE any GO

1. **Execution realism:** historical bid-ask quote/marketable-limit fill data around 09:45 NY, observed spreads, latency sensitivity, partial fills, earnings gaps, and conservative limit-price handling on gap-through-target bars. OHLC-based favorable `TARGET_GAP` open fills can overstate realizable upside.
2. **Prospective model OOS:** commit the exact signal and risk policy prior to a genuinely unseen time window; evaluate additional months without reselection and require adequate independent trades (especially B's n=7).
3. **Portfolio sizing / risk:** distinguish trade-level mean R from portfolio equity, quote-sensitive friction and capital-at-risk; verify drawdowns and risk budget.

**Final decision: KEEP EXPERIMENT; LIVE = HOLD.** Repricing or positive 2026 mean does not authorize deployment.
