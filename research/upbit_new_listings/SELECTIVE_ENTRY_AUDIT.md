# Selective-entry AI audit — 2026-10-26

Input: 170 post-crash, three-filter candidate entries; feature_asof_rows.csv. A **candidate-only** classifier, not a full-universe listing predictor. The 2026 slice has already been inspected in many previous experiments, so not a fresh untouched holdout.

Sequence: train 2023–24 (29), choose score quantile among top 50/30/20/10% on 2025 (81); minimum 10 selected to qualify. Refit 2023–25, apply frozen score quantile against training score distribution to 2026 (60).

Chosen percentile: top 20% by 2025 validation mean, n=17, validation mean -0.9539%, win 17.65%. Refitted 2026 selection n=12, mean net -2.1617%, win 8.33%, AUC 0.3882. 2026 all candidates n=60 mean -0.3750%, win 23.33%. Mean +20% target **FAILED**.

Warnings: 2023–24 training has n=29 only; overfitting likely. Significant selection bias from restricting to historical qualified entries. Dataset incomplete (no delisted symbols), no true real-world spread or depth, candle execution assumptions and 2026 exploratory reuse. No BUY activation. To rerun: add input CSV next to selective_entry.py and install numpy,pandas,scikit-learn.