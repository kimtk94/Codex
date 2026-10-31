# Kalman 5 US ETF/Equity Symbols — Jan–Oct Volume Robustness Review

**Verified:** 2026-10-31. **Scope:** SPY/IWM/SMH/MU/COIN, 2024–2026 adjusted Alpaca SIP 15-min bars. **Research-only, LIVE HOLD**.

## Reproducible evidence

- GitHub Actions **SUCCESS**: https://github.com/kimtk94/Codex/actions/runs/41201893245
- Artifact ID: `13042513993`, private Google Drive: https://drive.google.com/file/d/1MVG-38IlRBG1WQLXy_fO9znwf0mTNtVp/view?usp=drivesdk
- Inputs: exactly **711 complete NYSE RTH sessions per symbol**, **0 partial/missing sessions**.
- Matched outcome window: **Jan–Oct 2025, n=208** and **Jan–Oct 2026, n=208** signal days **per ticker**. Both signal day and its next-session return must be within the named month window.
- Prior-only training: 2025 train n=231, 2026 train n=481. Fixed 3 feature price model versus +2 completed-session relative-volume fields; both fitted on identical dates. Two distinct binary tasks: next NYSE session open-to-close **up/down**, and **large absolute move** using train-only 75th percentile cutoff.
- Paired moving block bootstrap: **400** repetitions using **5-session** contiguous blocks; each block uses identical indices for price and price+volume. CI levels **nominal 95% and uncorrected across multiple comparisons**. Historical test years have already been examined, so this is descriptive post-hoc robustness, not untouched prospective OOS.
- Brier Score: lower is better, negative `(volume minus price)` indicates incremental improvement. AUC: higher is better.

## Large-move probability Brier incremental effect (volume minus price)

| Ticker | 2025 Jan–Oct Δ | 2025 block 95% CI | 2026 Jan–Oct Δ | 2026 block 95% CI |
|---|---:|---:|---:|---:|
| IWM | **−0.02048** | **[−0.03715, −0.00735]** | **−0.01272** | **[−0.01840, −0.00747]** |
| SPY | −0.00012 | [−0.00264, +0.00230] | −0.00247 | [−0.00412, −0.00101] |
| MU | −0.00524 | [−0.01246, +0.00313] | −0.00580 | [−0.01022, −0.00112] |
| SMH | +0.00622 | [−0.00177, +0.01653] | +0.00323 | [−0.00267, +0.00708] |
| COIN | −0.00251 | [−0.01718, +0.01069] | −0.00018 | [−0.00123, +0.00122] |

**Critical benchmark failure:** in IWM, although adding volume reduces Brier vs the price-only model with nominal positive delta confidence, **both classifiers are worse than a constant prior-training event frequency baseline**:
- IWM 2025 large move: train-only constant baseline **0.20665**, price-only **0.26254**, price+volume **0.24206**.
- IWM 2026 large move: baseline **0.16361**, price-only **0.24427**, price+volume **0.23155**.
Thus do NOT call IWM volume signal deployable or objectively superior. A 0.02 difference relative to a poorly calibrated price-only classifier is not sufficient.

SMH large move worsens Brier in 2025 and 2026. SPY direction data are concerning, detailed below.

## Next-session direction task

| Ticker | 2025 Jan–Oct ΔBrier | 2026 Jan–Oct ΔBrier | Direct implication |
|---|---:|---:|---|
| SPY | **+0.01355** | +0.00591 | Price+volume worsens; 2025 bootstrap 95% **[+0.00889,+0.01951]**; AUC shift 2025 **−0.06907**, bootstrap CI **[−0.11042,−0.04173]** |
| IWM | +0.00432 | +0.00007 | No stable benefit |
| SMH | +0.00237 | +0.00006 | No stable benefit |
| MU | −0.00445 | +0.00306 | Year sign flips; no robust direction benefit |
| COIN | −0.00014 | +0.00052 | Small, mixed signs and AUC declining |

## Valid research decision

- **Data readiness GO** for the studied five tickers and 15-minute volume / VWAP / bar trade-count retrieval.
- **Relative volume as automatic direction predictor HOLD** for all tickers.
- **IWM high-volatility probability risk hypothesis: RESEARCH ONLY / HOLD**, despite nominal paired CI reduction; unconditional calibration baseline beats both.
- **SPY direction + volume: negative evidence**, especially 2025. Do not copy QLD model settings or feature gate to SPY.
- **Next work is a benchmark-calibration check**: re-run *identical* Jan–Oct cohorts for a constant training-prevalence model and **class_weight=None** logistic models, compared to existing balanced classifiers. This isolates whether the large-move Brier error came from training with `class_weight='balanced'`, not whether volume is generally useful.
- Even if calibration passes, require truly unseen forward data, familywise/multiplicity controls, transaction cost / TP-SL / MDD and risk veto ablation before any LIVE promotion.

### Related code

- `us_multisymbol_volume_screen.py`: 3-versus-5 feature initial test.
- `us_multisymbol_volume_robustness.py`: matched month, five-session paired CI, no-skill comparator.
- `us_multisymbol_volume_calibration.py`: follow-on train-prior, unweighted versus class-balanced analysis; **CI status must be verified before reporting a result**.
- Workflow: `.github/workflows/kalman-us-multisymbol-bars.yml`.
