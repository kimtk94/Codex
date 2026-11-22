# Frozen daily replay discrepancy reconciliation — 2026-11-22

**Status: research only, no LIVE execution or strategy promotion.** This document covers the existing legacy 2026-11-20 observation. It does not reconstruct or claim to possess the original unarchived 21-feature source fingerprint.

## Grounded historical findings

Existing [Issue #884](https://github.com/kimtk94/Codex/issues/884), [PR #889](https://github.com/kimtk94/Codex/pull/889), [PR #905](https://github.com/kimtk94/Codex/pull/905) and [PR #906](https://github.com/kimtk94/Codex/pull/906) documented the source and model-decomposition work prior to this incremental audit.

- Frozen Bull signals changed in **20/20 recomputed scores** for the 2026-11-20 completed NYSE session, but original event bytes and hashes remained unchanged.
- **4/20 material Bull incidents**, not 20 independent severe incidents: SPY +1.8623 percentage points, AMZN +1.6174pp, GOOGL +1.2434pp and NVDA +1.1668pp, with no candidate flips in the reported case.
- Three immutable actual Actions archives showed first daily 2026-11-20 adjusted close revised for **25/26** assets, and **24/26 >10bp**, while the prior history was not revised materially; full-history rescale was not the primary driver.
- Retrospective fixed-model counterfactuals attribute nearly all *observed* model score movement to changes in the signal-day feature vector, not stochastic repeated refitting under identical inputs. Public after-hours quote corroboration exists for five affected assets, **but the exact upstream vendor mechanism and primary-exchange official 16:00 close remain uncertified**.
- Bear replay differences (e.g. 32 changed-field records) count field changes, including feature/eligibility metadata. They **must not be equated** to Bull's 20 probability differences or to stability gate's 4 **material** incidents.
- The original first-seal **21-feature/fitted-model snapshots did not exist** for that historical session. No future re-run may retroactively create a fake sealed original input.

## What the automated additional audit does

`replay_drift_reconciliation.py` is run in the protected main Daily20 workflow after `forward_shadow.py`, `bear_forward.py`, and `stability_gate.py`. It reads their original read-only reports and `source_finality/report.json` from the **same completed session**. It does not read or write a trading account.

The program enforces symbol/date/family and 20+40 journal completeness; validates frozen event SHA-256 formats; independently reconstructs the Bull replay probability change (percentage points) and candidate flips; and reconciles its (>1)-percentage-point material flags to the stability gate's original **legacy event-only** incidents. It exports a deterministic per-symbol family audit CSV and JSON, both to the existing Drive **results** ZIP, preserving source report byte hashes and an explicit **no causal provider proof** field.

A brand-new session with a valid genuinely first-sealed input snapshot is handled independently; it is never represented as legacy input evidence. Misaligned probability changes/incident counts, false source certification, duplicate events, missing historical snapshot state, or malformed inputs fail closed.

## Future closure requirements

1. Capture **the first truly new completed XNYS session** before next open with all 26 OHLCV and 20×21 feature snapshots, 40 fitted-model input fingerprints and immutable Bull/Bear original event hash anchors; persist and read back the complete signed Drive ZIP.
2. Compare another run of that **same** new session against the first immutable snapshot and confirm snapshot digest unchanged while any legitimate data revisions are visible as a new replay event.
3. Obtain independently attributable official regular-session close and corporate-action factor evidence (price certification still **0/26**) and later genuinely settled 4-session prospective outcomes. No early return or source upgrade.

The overall implementation milestone score remains **7/10 (70%)**, and this is a visibility improvement inside unfinished reproducibility/source-validation milestones. The main pipeline's success is not scientific approval.
