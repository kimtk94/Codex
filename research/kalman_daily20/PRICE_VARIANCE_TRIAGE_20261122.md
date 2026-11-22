# Daily20 observed raw-vs-vendor price variance triage — 2026-11-22

**Research-only. No price replacement, no strategy promotion, no independently certified official closing price or corporate-action factor.**

## Inputs and basis
The preceding [price basis bridge](PRICE_BASIS_BRIDGE_20261122.md) supplies **26 contemporaneous records**: 25 equities/ETFs with a provisional Alpaca primary-venue SIP closing M print, a Yahoo historical `Close` (**split-adjusted**) and `Adj Close` (**dividend/split-adjusted**) where available, plus the Daily20 auto-adjusted model close. The Cboe VIX index (^VIX) has no stock-split/dividend adjustment and must not be classified as one of the 25. These values may differ even when none is erroneous.

The triage script `price_variance_triage.py` validates session, each price basis, 26 distinct symbols, factor self-consistency, provenance and raw source fingerprints from the preceding audited bridge. It calculates:

```
signed_price_difference_usd = raw_primary_M_usd - yahoo_split_adjusted_close_usd
signed_difference_bps = 10_000 * signed_price_difference_usd / raw_primary_M_usd
```

The denominator is the provisional raw M price. **No conversion of Yahoo split-adjusted prices to authenticated raw exchange prices is attempted.** In particular, a residual between these price conventions does not demonstrate a vendor error or a corporate-action cause.

## Diagnostic priority bands
| Bucket | Threshold | Action and interpretation |
|---|---|---|
| WITHIN_HALF_CENT_RESEARCH_ONLY | abs USD difference ≤ $0.005 | Low observed discrepancy; *not* certified close |
| OVER_HALF_CENT_UP_TO_10BPS | greater than $0.005, abs bps ≤ 10 | Review auction time/rounding and adjustment basis |
| OVER_10_UP_TO_50BPS | greater than 10 bps, ≤ 50 bps | Review primary exchange venue and timestamp provenance |
| OVER_50BPS_FACTOR_OR_VENUE_REVIEW | greater than 50 bps | Priority investigation into split units, corporate actions, auction records and vendor revisions; **cause unknown** |
| RAW_OR_VENDOR_REFERENCE_MISSING_HOLD | required series missing | Missing evidence; do not manufacture price or zero difference |

Review priority only. No band certifies equality or permits automatic trade approval. The reference may be a market-center M print rather than a consolidated 16:00 final close. Yahoo `Close` may already be adjusted for later splits.

## Artifacts and automation
- Program: [price_variance_triage.py](price_variance_triage.py); tests: [test_price_variance_triage.py](test_price_variance_triage.py).
- Input: `output/daily20/research/price_basis_bridge/report.json`. Its complete bytes are fingerprinted with SHA-256.
- Output: `output/daily20/research/price_variance_triage/report.json` and deterministic 25-row `review_queue.csv`. The CSV SHA-256 is recorded in the report.
- Daily20 GitHub Actions executes this **after** the price basis bridge, **before** trading research training, within the existing research-only pipeline. On successful protected `main` runs, both artifacts are published to the existing [Drive Daily20 results ZIP](https://drive.google.com/file/d/1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w/view).
- CI logs emit five bucket totals and the top eight largest absolute-bps observations without personal information or credentials. A missing external source is a visible missing-data HOLD record. Invalid source bytes, missing hashes, inconsistent factors, session mismatch and impossible values fail closed.
- Input OHLCV, feature snapshots, signal journal, model training, execution settings, broker access and Drive IDs are not modified.

## Scientific closure gates
Independent historical and same-session 16:00 official-close evidence, point-in-time listing venue identity, and issuer-verified split/distribution unit-basis history remain required. The unresolved QQQ 2018-06-18 and QLD 2023-09-20 cash events are **separate historical evidence gaps**, not automatically explanations for a November 2026 discrepancy. Research finality remains **0/26; overall project 7/10 milestones** until such proof exists.
