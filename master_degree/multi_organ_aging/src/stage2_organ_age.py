from __future__ import annotations

import argparse
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from moa_common import load_yaml, save_json


def healthy_reference(df: pd.DataFrame, cfg: dict) -> pd.Series:
    h = pd.Series(True, index=df.index)
    rules = cfg.get("healthy_reference", {})
    checks = {
        "metabolic__bmi": ("range", rules.get("bmi_range")),
        "metabolic__glucose": ("max", rules.get("glucose_max")),
        "metabolic__hba1c": ("max", rules.get("hba1c_max")),
        "vascular__sbp": ("max", rules.get("sbp_max")),
        "vascular__dbp": ("max", rules.get("dbp_max")),
        "renal__egfr": ("min", rules.get("egfr_min")),
    }
    for col, (kind, val) in checks.items():
        if col not in df or val is None:
            continue
        x = pd.to_numeric(df[col], errors="coerce")
        if kind == "range":
            h &= x.isna() | x.between(val[0], val[1])
        elif kind == "max":
            h &= x.isna() | (x <= val)
        else:
            h &= x.isna() | (x >= val)
    return h


def make_model():
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
        ("ridge", RidgeCV(alphas=np.logspace(-3, 4, 30))),
    ])


def fit_oof_ridge(X, y, groups, n_splits=5):
    unique_groups = pd.Series(groups).nunique()
    k = max(2, min(n_splits, unique_groups))
    gkf = GroupKFold(n_splits=k)
    oof = np.full(len(y), np.nan)
    for tr, va in gkf.split(X, y, groups):
        model = make_model()
        model.fit(X.iloc[tr], y.iloc[tr])
        oof[va] = model.predict(X.iloc[va])
    final = make_model()
    final.fit(X, y)
    return oof, final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_yaml(args.config)
    df = pd.read_parquet(args.panel).copy()

    baseline = df.sort_values(["subject_id","wave"]).drop_duplicates(
        "subject_id", keep="first"
    ).copy()
    baseline["healthy_reference"] = healthy_reference(baseline, cfg)

    score = df[["subject_id","wave","age","years_since_baseline","sex"]].copy()
    metrics = []

    for organ, spec in cfg["organ_domains"].items():
        feats = [
            c for c in df.columns
            if c.startswith(organ + "__") and df[c].notna().sum() >= 50
        ]
        if len(feats) < int(spec["required_min_features"]):
            metrics.append({
                "organ": organ, "status": "insufficient_features",
                "n_features": len(feats)
            })
            continue

        tr = baseline[baseline["healthy_reference"] & baseline["age"].notna()].copy()
        usable = [c for c in feats if tr[c].notna().sum() >= 30]
        if len(usable) < int(spec["required_min_features"]) or tr["subject_id"].nunique() < 100:
            metrics.append({
                "organ": organ, "status": "insufficient_reference",
                "n_features": len(usable), "n_ref": len(tr)
            })
            continue

        oof, model = fit_oof_ridge(
            tr[usable].reset_index(drop=True),
            tr["age"].reset_index(drop=True),
            tr["subject_id"].reset_index(drop=True),
        )
        bias = LinearRegression().fit(tr[["age"]], oof)

        pred_all = model.predict(df[usable])
        expected_pred = bias.predict(df[["age"]])
        bag = pred_all - expected_pred

        score[f"{organ}__pred_age"] = pred_all
        score[f"{organ}__bag"] = bag
        rmse = float(np.sqrt(np.nanmean((oof - tr["age"].to_numpy()) ** 2)))
        r = float(np.corrcoef(oof, tr["age"].to_numpy())[0,1])
        metrics.append({
            "organ": organ,
            "status": "ok",
            "n_features": len(usable),
            "features": "|".join(usable),
            "n_reference": len(tr),
            "oof_rmse": rmse,
            "oof_r": r,
            "bias_intercept": float(bias.intercept_),
            "bias_slope": float(bias.coef_[0]),
        })
        joblib.dump(
            {"model": model, "bias_model": bias, "features": usable},
            out / f"MODEL_{organ}.joblib"
        )

    score.to_parquet(out / "STAGE2_ORGAN_AGE_SCORES.parquet", index=False)
    pd.DataFrame(metrics).to_csv(
        out / "STAGE2_MODEL_METRICS.tsv", sep="\t", index=False
    )
    save_json(
        {"organs_ok":[m["organ"] for m in metrics if m["status"]=="ok"]},
        out / "STAGE2_SUMMARY.json"
    )
    print(pd.DataFrame(metrics).to_string(index=False))


if __name__ == "__main__":
    main()
