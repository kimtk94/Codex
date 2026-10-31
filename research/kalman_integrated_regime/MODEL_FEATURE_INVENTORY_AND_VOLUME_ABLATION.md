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
