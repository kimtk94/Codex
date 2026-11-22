# Daily20 20-name replay: model runtime and package attestation — 2026-11-22

**Implementation remains 7/10 (70%)**; outstanding scientific acceptance gates: independent price/CA finality, stable first-seal/same-day model input replay, and genuine 4-XNYS-session settlements. This improvement is **diagnostic, not scientific completion**.

## What the existing evidence already supports

- Frozen 2026-11-20 Bull events were byte-identical in later pinned Drive results; **20/20** recomputed probabilities differed, **4** by more than 1 percentage point, with no observed candidate flips. The original as-of 21 feature and fitted-model snapshot was **not** captured on that legacy session.
- Retrospective immutable GitHub artifacts (documented in #884, PR #905/#906) showed **25/26** adjusted daily closes changed, **24/26** had terminal close differences over 10bp. Paired fixed-model counterfactual decompositions attributed most *observed* score change to as-of feature revisions, not an inability to refit deterministic code from the *same* inputs. This is historical evidence, not a newly verified cause of a publisher correction.
- The current workflow installs wide ranges (`pandas>=2.2,<3`, `numpy>=2,<2.4`, `scikit-learn>=1.6,<2`, `pyarrow>=17,<25` in contracts; a separate market-data requirements file in the research job). Different resolved environments may change numerical results, especially native parsing/BLAS. An actual two-run protected main native Pandas C-parser segmentation fault was opened as #981; using a Python parser only in a test contains the failure, not a proven root cause.

## New read-only runtime lineage

`model_runtime_lineage.py` creates a metadata-only immutable-per-artifact report without saving credentials or all environment variables. It records:

- Python version, ABI, host machine/system, whitelisted BLAS/Arrow thread settings.
- Actual installed versions and SHA256 of wheel `RECORD` metadata for numpy, pandas, SciPy, scikit-learn and pyarrow; selected *installed native extension binary bytes* are SHA256-digested separately. TA-Lib and yfinance are advisory and may be absent from contracts. RECORD alone is not trusted as a binary-content hash.
- Exact source SHA256 for 6 inference/forward code modules and the market-data requirement file, separately from execution environment.
- The independent **contracts** job writes `contract_environment/report.json` and publishes a short-retention Actions artifact. The **research** job downloads that report and compares shared required native packages, code, Python ABI, and whitelisted thread configuration. Differences are documented; an environment mismatch does not invent a market price or halt the independent research analysis.
- Protected `main` additionally loads the prior pinned results ZIP, checks the previous runtime JSON member against the signed SHA256 in `drive_manifest.json`, compares *only if the prior environment exists*, separates same-session versus cross-session comparisons, and ties results to the current session's `replay_drift_reconciliation` and `stability` reports. PR has no private prior ZIP and does not invent a baseline.
- The canonical output `research/model_runtime_lineage/report.json` is included by the existing ZIP publisher; SHA256 and remote upload/readback remain the existing isolated Drive steps.

## Readout contract

- `PRIOR_ARCHIVE_REPORT_MISSING_LEGACY_HOLD`: older results ZIP lacks this new metadata. Do **not** backfill an old installation based on today's dependencies.
- `SAME_SESSION_RUNTIME_MATCH_RESEARCH_ONLY`: versions, wheel metadata, selected native binaries, code and settings match **two distinct actions runs**. This is not proof that adjusted OHLCV or features matched.
- `SAME_SESSION_RUNTIME_DIFFERENCE_RESEARCH_HOLD`: at least one critical environment dimension differs; identify package/field and evaluate independently of price/source revisions.
- `CROSS_SESSION_RUNTIME_MATCH_NOT_REPLAY_PROOF` or `CROSS_SESSION_RUNTIME_CHANGED_NOT_CAUSAL_PROOF`: environment continuity across different trading sessions, never incorrectly called a price/replay comparison.
- Any malformed previous ZIP member manifest, missing input validation, future-dated prior session, false finality, inconsistent run IDs, or report session conflict fails CI instead of a green result.

The next true first-sealed new session must still reproduce exactly the 26 market close inputs, 20×21 feature vectors, 40 fitted-model hashes and 60 event hashes across **independent** scheduled runs. This runtime ledger is a fifth independent attribution axis, not a replacement for existing stability verification.

## Operations constraints

Existing market prices, historical source adjustments, 20 stock strategies, package **install ranges**, first-sealed journals, model thresholds and trading account writes are unchanged. No local server needed; CI and Drive are the only persistent execution/storage components. If a future environment difference is observed, pin one reproducible set of tested dependencies as a separate PR after validation rather than changing runtime versions blindly now. Research and LIVE statuses remain **HOLD**.
