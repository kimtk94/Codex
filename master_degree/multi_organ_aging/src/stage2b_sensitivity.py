from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNetCV, RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from moa_common import load_yaml


def models() -> dict:
    alphas = np.logspace(-3, 3, 25)
    return {
        "ridge": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", RidgeCV(alphas=alphas)),
        ]),
        "elastic_net": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", ElasticNetCV(
                l1_ratio=[0.1, 0.25, 0.5, 0.75, 0.9],
                alphas=alphas,
                cv=5,
                max_iter=20000,
            )),
        ]),
        "hist_gb": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingRegressor(
                max_iter=300,
                learning_rate=0.05,
                l2_regularization=1.0,
                random_state=20260927,
            )),
        ]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    df = pd.read_parquet(args.panel)
    cfg = load_yaml(args.config)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    base = (
        df.sort_values(["subject_id", "wave"])
        .drop_duplicates("subject_id", keep="first")
        .dropna(subset=["age"])
        .reset_index(drop=True)
    )

    rows = []
    for organ, spec in cfg["organ_domains"].items():
        feats = [
            c for c in base.columns
            if c.startswith(organ + "__") and base[c].notna().sum() >= 50
        ]
        if len(feats) < int(spec["required_min_features"]):
            continue

        k = min(args.folds, base["subject_id"].nunique())
        if k < 2:
            continue
        splitter = GroupKFold(n_splits=k)

        for model_name, template in models().items():
            pred = np.full(len(base), np.nan)
            for tr, va in splitter.split(base[feats], base["age"], base["subject_id"]):
                # Recreate the estimator for every fold.
                estimator = models()[model_name]
                estimator.fit(base.iloc[tr][feats], base.iloc[tr]["age"])
                pred[va] = estimator.predict(base.iloc[va][feats])

            ok = np.isfinite(pred)
            y = base.loc[ok, "age"].to_numpy()
            p = pred[ok]
            rows.append({
                "organ": organ,
                "model": model_name,
                "n": int(ok.sum()),
                "n_features": len(feats),
                "rmse": float(mean_squared_error(y, p) ** 0.5),
                "mae": float(mean_absolute_error(y, p)),
                "r": float(np.corrcoef(y, p)[0, 1]) if len(y) > 2 else np.nan,
            })

    res = pd.DataFrame(rows).sort_values(["organ", "rmse"])
    res.to_csv(out / "STAGE2B_MODEL_SENSITIVITY.tsv", sep="\t", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
