# US 5-Symbol Historical Volume Predictor Ablation — First Empirical Scoreboard

**Verified:** 2026-10-31. **Repository:** kimtk94/Codex, `research/qld-integrated-regime-20261031`; **PR:** #477.  
**Run:** https://github.com/kimtk94/Codex/actions/runs/41198775759 — contracts PASS, 2024–2026 SIP 15m private backfill PASS, predictive screening PASS.  
**Archive:** https://drive.google.com/file/d/15xVJ9Haqv_bq_P5Hme6DJ8KwPXoU9Xw5/view?usp=drivesdk — verified source_qa.json and predictive_screen.json; aggregate-only; licensed SIP raw bars not uploaded.

## Exact experiments

- SPY, IWM, SMH, MU, COIN each have **711 complete RTH sessions**, no missing sessions on this source window; 221,014 total 15m bars. Daily feature at **completed current close**, earliest potential decision next US session.
- Binary outcomes: **next session open→close return positive** (`direction_up`), and **next-session |open→close return| ≥ prior-training 75th percentile** (`next_session_large_move`).
- Price 3: trailing 5/20-session price returns and 20-session realized price log-return volatility.
- Price+volume 5: same 3 + symbol-specific completed RTH RVOL20 and volume Z20 (previous 20 sessions only).
- Separate per-symbol class-weight-balanced logistic models, 2025 train `n=231`, test `n=249`; 2026 YTD train `n=481`, test `n=208`. Exactly identical training and test date cohorts within each price-vs-volume paired evaluation; 2025 and 2026 have different, not yet matched, calendar coverage.
- **NOT a profitability backtest.** No commission, spread, slippage, financing, order execution, position sizing or live risk gates. This is also **not untouched OOS**, since these years were used in prior research.

### AUC (price only → price+volume) for **next session up/down**

| Ticker | 2025 | 2026 YTD | Delta in AUC, 2025 / 2026 |
|---|---|---|---|
| SPY | .5368 → .4722 | .5245 → .4815 | **−.0645 / −.0430** |
| IWM | .5454 → .5475 | .5167 → .5287 | +.0021 / +.0120 |
| SMH | .5260 → .5298 | .4849 → .5116 | +.0038 / +.0267 |
| MU | .4876 → .4923 | .4904 → .4822 | +.0046 / −.0081 |
| COIN | .5590 → .5557 | .5661 → .5430 | **−.0033 / −.0231** |

**Do not infer that AUC increases alone justify a new model.** SPY and COIN direction-discrimination worsened in both years. IWM and SMH modestly improve AUC but *Brier/log-loss worsen in both years* for the direction target, indicating calibration/fit conflict.

### AUC (price only → price+volume) for **next session large absolute move**

| Ticker | 2025 | 2026 YTD | Delta in AUC, 2025 / 2026 |
|---|---|---|---|
| SPY | .7298 → .7259 | .6519 → .6574 | −.0039 / +.0055 |
| IWM | .4196 → .5647 | .5620 → .5478 | **+.1451 / −.0142** |
| SMH | .6372 → .5831 | .6341 → .6251 | **−.0541 / −.0090** |
| MU | .5967 → .5770 | .5183 → .5349 | −.0197 / +.0167 |
| COIN | .5312 → .4324 | .5213 → .5017 | **−.0988 / −.0196** |

**Brier differences (volume−price; negative means improvement)** for next-session large-move target:

| Ticker | 2025 | 2026 YTD | Comment |
|---|---:|---:|---|
| SPY | −.0003947 | −.0024719 | small Brier improvement in both years, AUC mixed |
| IWM | **−.0220089** | **−.0127240** | Brier/logloss improve in both, AUC mixed |
| SMH | +.0066560 | +.0032330 | all metrics deteriorate in both |
| MU | −.0045246 | −.0058005 | Brier/logloss improve, AUC mixed |
| COIN | −.0005160 | −.0001837 | tiny Brier improvement, AUC worsens substantially in 2025 |

**Direction target Brier differences (volume−price):**

| Ticker | 2025 | 2026 YTD |
|---|---:|---:|
| SPY | +.0121173 | +.0059102 |
| IWM | +.0035982 | +.0000679 |
| SMH | +.0010527 | +.0000620 |
| MU | −.0044039 | +.0030631 |
| COIN | +.0001038 | +.0005156 |

## Interpretation and required next gate

1. **Prediction objective matters:** trading-volume variables are not uniformly informative for price *direction*. For IWM, SPY and MU they may improve *probability error for large moves*, a different classification problem that still needs out-of-period calibration, fees and actual risk-policy impact.
2. **Distinguish AUC from Brier/logloss.** The classifier uses `class_weight='balanced'`, so raw model probabilities need not be calibrated for next-session large-move base rates. Improvement vs price-only alone is insufficient; compare a no-skill training-prevalence benchmark as a baseline.
3. **Preserve term definitions:** `price_logvol20` is **price volatility**, not volume. Added volume fields are `rvol20`, `volume_z20`; bid/ask aggressor-side remains a separate, not-yet-validated source family.
4. **Correct year length asymmetry:** restrict **both** 2025 and 2026 evaluation to Jan–Oct; keep prior-year label-exit purge, and quantify paired score delta uncertainty with day-block resampling. This is a research sensitivity analysis, NOT a fresh prospectively held-out test.
5. **Strict HOLD:** no ticker receives automatic volume-model upgrade or live trading change on current results. Any next selection requires independent prospectively unseen data and a per-stock TP/SL/holding/cost ledger, not just AUC.

**Next robust CI implementation:** `us_multisymbol_volume_robustness.py` + tests and `.github/workflows/kalman-us-multisymbol-bars.yml` modified to publish `matched_months_robustness.json` within the existing ephemeral bar job. Pending run at authoring: https://github.com/kimtk94/Codex/actions/runs/41201668802. No CI/robustness status should be called PASS until verified.

### Evidence chain

- Source data and 711-session source completeness: https://github.com/kimtk94/Codex/actions/runs/41198243032 .
- First paired volume-model experiment: https://github.com/kimtk94/Codex/actions/runs/41198775759 .
- Original QLD/QQQ 5/9/10/14 input audit: `MODEL_FEATURE_INVENTORY_AND_VOLUME_ABLATION.md`.
- Per-ticker transport/quote access feasibility: https://github.com/kimtk94/Codex/actions/runs/41191170517 .
