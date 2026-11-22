# Daily20 20-core real-data NumPy/PyArrow version matrix — 2026-11-22

**Progress 7/10 (70%) · 3 scientific acceptance tasks remain · LIVE HOLD.** This is a controlled **research experiment**, not a new data supplier, market signal, trading rule, or finality certificate.

## Experimental input provenance

A protected 2026-11-20 Daily20 Actions run [#45033994883](https://github.com/kimtk94/Codex/actions/runs/45033994883) uploaded its **26 raw yfinance Parquet assets + 26 TA-Lib feature Parquets** to the immutable GitHub Actions artifact named `kalman-daily20-data` (first page artifact ID `14759195629`). It was produced **before** the 2026-11-23 U.S. session. Its date-specific values are retrospective research inputs; historical publisher 16:00 close accuracy remains 0/26 unverified.

A dedicated workflow `.github/workflows/kalman-daily20-runtime-matrix.yml` downloads **that exact main run ID and artifact name**. The preparation job authenticates 52 file SHA-256s, records byte sizes, 26 unique symbols, the fixed 2026-11-20 as-of date, a 20-row synthetic settlement **parser fixture only**, and publishes one frozen private Actions artifact. Both experiments download these exact bytes; independent checksum validation rejects any change.

The **real pricing/feature data** and existing research model code are identical. The C-parser fixture is explicitly synthetic to reproduce crash behavior and never entered into forward settlement/portfolio histories.

## Two controlled Python 3.11 environments

| | Baseline (contract-like) | Research (actual-like) |
|---|---|---|
| NumPy | 2.3.5 | 2.4.6 |
| PyArrow | 24.0.0 | 26.0.1 |
| Pandas | 2.3.3 | 2.3.3 |
| SciPy | 1.17.1 | 1.17.1 |
| scikit-learn | 1.9.1 | 1.9.1 |

Both use fixed OpenBLAS/OMP/MKL/Arrow thread settings = 1. Models call existing `provenance_audit.predict_on_frame` / `train.model_year` / `regime_challenger.fit_bear_year` unchanged for **20 core symbols × 2 Logistic families = 40** annual-expanding fits/research predictions. SPY and NVDA refit a second time inside each environment to measure within-environment repeatability. Per model record: real signal-day 21-feature SHA256, actual training data SHA256, training sample counts, model parameter/coefficient digest, status and probability.

The comparator requires **40 matching symbol/family keys**, identical run-anchored input manifest, identical model code, identical date, identical feature and training digests. If model probabilities differ under those constraints, it reports runtime numerical sensitivity in percentage points, not a verified explanation for the historical missing original 21 features.

## Native parser containment experiment

The 2026-11-22 [#981](https://github.com/kimtk94/Codex/issues/981) Pandas C parser crash occurred in a *full-suite* test on `outcomes.csv` and is not automatically reproduced by independent probes. Each version runs a bounded 150-iteration **C parser** and **Python parser** probe on the same synthetic 20-row settlement-schema CSV; *each engine runs in its own child process*. A native segfault can yield `CRASH_OR_ERROR_RESEARCH_HOLD`, captured with exit code and stderr, without hiding comparison results or corrupting the main trading research pipeline. Passing isolated parser probes is **not** proof that the previous full-suite segfault's root cause is solved.

## Artifact contract and scientific limitations

- `daily20-fixed-real-input-20261120`: 52 original data files plus full manifest/checksums and isolated synthetic parser fixture (retained 14 days; no credentials).
- `daily20-runtime-matrix-baseline`, `daily20-runtime-matrix-research`: one original 40-model diagnostic JSON per pinned Python stack (retained 21 days).
- `daily20-runtime-matrix-comparison`: per-symbol Bull/Bear prediction differences, training/feature equality checks and native parser results; integrity manifest, retained 90 days.
- The old 2026-11-20 Bull first-signal **21-feature / model snapshot was not archived on initial seal**, so one immutable later data artifact cannot retroactively reconstruct it; status stays **RESEARCH HOLD**.
- If prediction deltas are zero, that only shows **these two pinned version combinations** agree on **this one captured real archive**. It cannot rule out numerical instability in other historical jobs or explain why the original Yahoo bar changed.
- Existing 60 sealed forward events and their later 4-XNYS-session settlements are never modified, created, backfilled, or promoted by this experiment.
- No historical official close, source price/corporate-action factor certification or trading performance claim is generated.
- The experiment is separate from the protected daily production research workflow and will not run on a schedule; only relevant PR/push/explicit workflow dispatch. The existing daily two-run forward replay cadence is unchanged.

## Decision

Adopt a pinned environment in the daily Kalman research workflow **only after** this matrix has a clean, audited comparison across all 40 fitted models, a reviewed data/source trace, and follow-up real forward-seal consistency evidence. **Neither a green matrix nor a native-parser PASS grants LIVE approval.**
