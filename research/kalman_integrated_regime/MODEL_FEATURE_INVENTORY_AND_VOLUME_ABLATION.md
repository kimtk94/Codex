# Kalman QLD / QQQ model feature registry and P0 volume follow-up

**Frozen at:** 2026-10-31 · **Branch:** `research/qld-integrated-regime-20261031` · **PR:** #477  
**Authority:** Research-only. This inventory is of `research/kalman_integrated_regime/` and is **not** an audit of all Kalman LIVE components.

## 1. The exact 10 features used to fit the current QLD models

Source: `research/kalman_integrated_regime/run.py`, constants `PRICE`, `EXTRA`, `MARKET`, function `build_features`. Train/test model `StandardScaler + LogisticRegression(C=1, class_weight=balanced, random_state=42)`.

| Name | Formula / meaning | Source | Temporal point of availability | Price 5 | Integrated 10 |
|---|---|---|---|---|---|
| `qqq_r5` | 5-session QQQ close return | SIP QQQ session close | after current regular close | yes | yes |
| `qqq_r20` | 20-session QQQ close return | SIP QQQ session close | after current regular close | yes | yes |
| `qld_r5` | 5-session QLD close return | SIP QLD session close | after current regular close | yes | yes |
| `qqq_vol20` | 20-session std. deviation of log daily returns | SIP QQQ session close | after current regular close | yes | yes |
| `qld_minus_2qqq` | QLD 1-day return minus 2 × QQQ 1-day return | SIP QLD/QQQ session close | after current regular close | yes | yes |
| `vix_lag1` | yesterday's VIX level | yfinance / `yf_vix` | prior daily session | no | yes |
| `vix_r5_lag1` | yesterday's VIX 5-session change | yfinance / `yf_vix` | prior daily session | no | yes |
| `hyg_lqd_r5_lag1` | 5-session HYG return minus LQD return, lagged | yfinance / `yf_hyg`, `yf_lqd` | prior daily session | no | yes |
| `tnx_lag1` | previous TNX value | yfinance / `yf_tnx` | prior daily session | no | yes |
| `smh_spy_r20_lag1` | 20-session SMH minus SPY return, lagged | yfinance / `yf_smh`, `yf_spy` | prior daily session | no | yes |

**Terminology warning:** `qqq_vol20` means **volatility**, not trading **volume**. No trading-volume variable is in the original 5- or 10-column model.

**Source universe:** Historical SIP adjusted 15-minute QLD/QQQ bars (`sip_backfill.py`) and six yfinance daily market proxies bundled privately. Prices and trade labels use the original 15-minute conservative barrier replay. 2025 and 2026 are used for yearly research evaluation. **FRED and USD/KRW are explicitly excluded** in the original research report; that does not establish the entire Kalman LIVE feature set.

## 2. Other data / controls used without classifier training

| Field | Actual use | Distinction |
|---|---|---|
| QLD 15-minute open / high / low / close | next-session entry, TP / SL collisions, path-dependent exits and full portfolio simulation | Used in **simulation and labels**, not a 15m-time-series neural predictor |
| QQQ 15-minute OHLC | source of QQQ daily close | daily price features only |
| QLD/QQQ 15-minute `volume` (`v`) | **Downloaded** and saved in private Parquet, until P0 now **not included in classifier** | No evidence it was excluded because it did not improve performance |
| 40-axis policy: `tp`, `sl`, `hold`, `size`, splits, trailing/BE, VIX/trend/confidence/gap filters, etc. | Jointly varied **after** model probabilities are fit | **40 execution knobs are NOT 40 ML training features** |
| Historical `n` trade count, `vw` VWAP | available in Alpaca bar payload, not retained by existing `sip_backfill.py` | do not treat as already historical-collected |
| SIP individual trades | separate read-only entitlement probe, historical one-minute PASS | not yet used in training or multi-year feature history |
| Top-of-book quotes, level-2 depth, institution identity | not in current research models | require separate sources and eligibility checks |
| Options OI/put-call, earnings, news, order flow, breadth, FINRA ATS | not included in this particular QLD research model | source/history and timestamp semantics unverified for this study |

## 3. P0 candidate volume variables and exactly what is being tested

Source: `research/kalman_integrated_regime/volume_features.py`.

- `qqq_rvol20`: completed-session QQQ volume ÷ **median of previous 20** complete-session QQQ volumes.
- `qld_rvol20`: analogous QLD relative volume.
- `qqq_volume_z20`, `qld_volume_z20`: daily completed-session volume minus prior 20-session mean, divided by prior 20-session std. A zero std is missing, not an artificial 0 z-score.
- `qld_qqq_rvol20_diff` and >2x-volume flags are calculated for diagnostics, **not** included in P0 model input. The RVOL difference is algebraically redundant when both component RVOLs are already inputs.
- A single missing 15m RTH bar makes daily volume missing. A volume feature is not available until market close; entry occurs no earlier than the **next** NYSE session.

| Arm | Model inputs | Model role |
|---|---|---|
| A `A_price_5` | original PRICE 5 | unchanged reference |
| B `B_price_volume_9` | PRICE 5 + volume 4 | volume-only increment without macro inputs |
| C `C_integrated_10` | PRICE 5 + EXTRA 5 | unchanged integrated reference |
| D `D_integrated_volume_14` | PRICE 5 + EXTRA 5 + volume 4 | volume increment over the integrated reference |

Source: `research/kalman_integrated_regime/volume_four_arm.py`. All arms are re-trained **on exactly the same nonmissing training and test signal dates** for each year; labels are purged when the trade exit overlaps the next test year; no tuning of classifier confidence or trade parameters. Fixed TP +3%, SL -3%, maximum 4 NYSE sessions, 10bp fee per side, 0.5 prediction threshold, same intrabar stop-first rule. Report annual return, MDD, trade count, Brier/log-loss/AUC and AB/CD paired differences. If missing macro or volume history removes rows, the comparisons cannot naively be equated to earlier reports evaluated on different cohorts.

**Execution:** `.github/workflows/kalman-qld-volume-ablation.yml`, read-only private Alpaca SIP / market bundle; only aggregate reports in Actions, temporary raw provider data erased.

**Gates:** Unit tests PASS (leakage, missing bar and locked cohorts) → complete 2024–2026 SIP/market download → full run PASS → A/B/C/D 2025 and 2026 matched observations and costs PASS → classify B vs A, D vs C as increase/decrease/unclear. A model with better raw return but materially worse MDD, fewer trades or poor probability calibration is not an automatic GO. **Any later 40-axis policy search is separate**.

## 4. Outcomes already verified from previous steps (not P0 volume results)

- Full `10,001 × 2 × 2 × 2 = 80,008` policy replays artifact: [GitHub Actions #41185397422](https://github.com/kimtk94/Codex/actions/runs/41185397422), ZIP artifact ID `13037726825`.
- 10,000 *structured* random candidates with 0–4 restrictive gates yielded **7,028 PRICE** and **7,487 INTEGRATED** policies with >=15 trades **in each** of 2025 and 2026. Both-year positive among those: **114 / 186**; very small shares are positive despite plentiful qualifying trades. These are extreme multiple-search exploratory figures, not untouched OOS.
- Historical single-minute Alpaca SIP Trades probe ([Actions #41188163034](https://github.com/kimtk94/Codex/actions/runs/41188163034); artifact ID `13037802056`) **PASS** with full pagination on **2026-10-29T15:00:00Z–15:00:59.999999Z**:
  - QQQ: 2,995 prints, 155 prints >=$100k, five >=$1m.
  - QLD: 252 prints, one print >=$100k, zero >=$1m.
  - This proves **one historical minute of account access**, not full historical coverage, correct correction-chain dedupe, full-session reliability, institution identity or aggressor side.
- Original volume synthetic contract run [#41188599884](https://github.com/kimtk94/Codex/actions/runs/41188599884) **PASS**.

**NEXT:** validate actual four-arm historical results, check volume-adjustment/split effects, and investigate P1 (`n`/`vw`) or P2 (large-print distribution) only after incremental benefit can be measured under fixed execution. LIVE remains unchanged.


## 5. Verified four-arm P0 result — HARD HOLD for indiscriminate volume addition

**GitHub Actions:** https://github.com/kimtk94/Codex/actions/runs/41189564936 — contracts **PASS**, historical evaluation **PASS**. Derived artifact ID `13038281932`; private Drive archive https://drive.google.com/file/d/1pJX-5DzHDKoH38DX0OQAO-Nsj56nY2zG/view?usp=drivesdk.

**Data gate:** 711/711 regular NYSE sessions for **both** QLD and QQQ, 1,422/1,422 complete instrument-session rows; 0 partial/missing for this fixed historical window; 691 daily rows per symbol have prior-20-session RVOL. Paired signal-label cohorts: train 228, test 246 in 2025; train 477, test 205 in 2026 YTD.

| Same fixed 3% TP / 3% SL / 4-session policy | 2025 return | 2025 daily-MTM MDD | 2025 completed trades | 2026 YTD return | 2026 daily-MTM MDD | 2026 completed trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A price-5 | -8.0971% | -23.8276% | 63 | -19.9081% | -26.1292% | 47 |
| B price+volume-9 | -1.9087% | -21.5945% | 59 | -32.3772% | -37.1380% | 56 |
| C integrated-10 | +0.3170% | -21.9055% | 61 | -20.6414% | -24.8970% | 58 |
| D integrated+volume-14 | +1.7673% | -16.6612% | 64 | -27.1281% | -33.5000% | 65 |

**Volume-only incremental contrasts:** B−A: +6.1884 percentage points in 2025, **−12.4691 pp** in 2026. D−C: +1.4503 pp in 2025, **−6.4867 pp** in 2026. 2026 drawdown also worsens **11.0088 pp** (B−A) and **8.6030 pp** (D−C).

**Classifier scoring deterioration:** 2025 AUC A→B `0.5249867→0.5115938`, C→D `0.5670975→0.5579691`; 2026 A→B `0.4533600→0.4525985`, C→D `0.4957167→0.4735389`. Brier and log loss also **worsen** in every matched comparison, despite higher 2025 trading return. P0 volume features are **not demonstrably additive predictive signal** under this frozen formula.

**Decision split:**
- P0 collection/data readiness **GO** for the tested history (complete regular sessions, verified reproducibility).
- P0 model addition **HOLD**: do **not** simply add all four volume variables to the existing model, do not enable LIVE, do not claim feature significance.
- Next analyses need exact 2025→2026 feature drift and regime interaction attribution; test alternate formulations and filtering **only under training-only feature selection / nested purged walk-forward** and validate on subsequent genuinely unseen periods. A trade-count/return improvement on one old year is insufficient.
- P1 bar VWAP/count and P2 print sizes are **separate data families**, not proven predictive by this P0 test.
- Historical 1-minute SIP print-access probe **PASS**, but full historical print reliability and condition-correction audit remain HOLD.

**All prior 40-axis policy results remain frozen and LIVE execution untouched.**

## 6. P0 2025 vs 2026 volume-regime and signal-switch audit (verified 2026-10-31)

**CI PASS:** https://github.com/kimtk94/Codex/actions/runs/41190183789; aggregate artifact ID `13038158735`. Private Drive: https://drive.google.com/file/d/1awfFRqb6v0CB4NhzhiHkkKIKFUVQHVf2/view?usp=drivesdk

Code: `volume_regime_drift.py`. For each year re-fits the exact original A/B/C/D logistic regressions to the **same dates**, then partitions test signal days into: both arms enter, volume-only enters, original-only enters, neither. For each group record **fixed 3%/3%/4-session candidate-label** positive fraction and corresponding QLD/QQQ relative-volume quantiles. **Candidate labels are NOT independently executed non-overlapping position outcomes.**

| Feature on complete paired signal-day cohorts | 2025 (246 dates) | 2026 through Oct (205 dates) |
| --- | ---: | ---: |
| QLD RVOL20 median | 1.0040 | 0.9875 |
| QLD RVOL20 p99 | 4.6716 | 2.6265 |
| QQQ RVOL20 median | 1.0100 | 0.9705 |
| QQQ RVOL20 p99 | 2.6773 | 2.2320 |
| fraction QQQ trailing 5-session return <0 | 38.21% | 49.27% |
| positive fixed-barrier label fraction | 54.47% | 49.76% |
| 20-session QQQ volatility median | 0.01154 | 0.01097 |
| prior VIX median | 17.24 | 17.16 |

**Integrated C vs D signal reclassification:**
- 2025: C/D both signal **111** days / positive label **58.56%**; D-only added **21** / **47.62%**; C-only removed **31** / **51.61%**.
- 2026: C/D both signal **103** / **47.57%**; D-only added **22** / **40.91%**; C-only removed **14** / **71.43%**.
- Therefore an important mechanism **consistent with** inferior 2026 results is that volume inclusion pushed low-label-hit candidate dates above 0.5 and some high-label-hit days below it. **This is descriptive only**: adding a candidate may block later overlapping entries; it does not prove that all return differences come from these 36 dates.
- 2025 P&L improved even though added-signal label fraction was weaker than removed-signal fraction. Selection overlap, trade sequencing, holding exposure, the sizes of gains/losses and differences in signal probability can alter portfolio P&L beyond binary candidate labels. Do NOT present volume as a positive label predictor in 2025.

**Price A vs B signal reclassification:**
- 2025: B-only added **33** / positive labels **42.42%**; A-only removed **41** / **53.66%**.
- 2026: B-only added **21** / **52.38%**; A-only removed **19** / **57.89%**.
- This demonstrates why *just counting model-selected trades or comparing annual totals does not identify feature usefulness*.

**Important date-cohort caveat:** 2025 contains a full year, whereas 2026 is year-to-date through October. Different seasonal composition and unequal samples can contribute to these differences; a January–October matched-calendar check is needed before strong regime-shift claims.

**Next scientific gates:** (i) matched-month sensitivity, (ii) sign/size and overlap of *actually executed* trades, (iii) training-only feature standardization and genuine post-selection OOS, and (iv) independent P2/P3 historical quote-matched aggressor estimates. Do not treat output as causal, and keep LIVE HOLD.
