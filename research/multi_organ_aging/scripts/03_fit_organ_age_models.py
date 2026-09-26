#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT = Path("/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging")
PANEL = Path("/srv/is-analysis/results/multi_organ_aging/stage1_panel/LONGITUDINAL_ORGAN_PANEL.tsv.gz")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage2_organ_age")
CFG = yaml.safe_load((PROJECT / "config/organ_panels.yaml").read_text())
SEED = int(CFG["project"]["random_state"])


def baseline_rows(panel: pd.DataFrame) -> pd.DataFrame:
    idx = panel.groupby("subject_id")["visit_index"].idxmin()
    return panel.loc[idx].copy()


def usable_features(df: pd.DataFrame, requested: list[str]) -> list[str]:
    out = []
    for c in requested:
        if c in df and df[c].notna().sum() >= 50 and df[c].nunique(dropna=True) > 2:
            out.append(c)
    return out


OUT.mkdir(parents=True, exist_ok=True)
panel = pd.read_csv(PANEL, sep="\t", low_memory=False)
base = baseline_rows(panel)
base = base[pd.to_numeric(base["AGE"], errors="coerce").notna()].copy()
base["AGE"] = pd.to_numeric(base["AGE"], errors="coerce")

all_preds = []
baseline_oof = []
metadata = {}

for organ, requested in CFG["organs"].items():
    feats = usable_features(base, requested)
    if len(feats) < 2:
        metadata[organ] = {"status": "skipped", "reason": "fewer than 2 usable features", "features": feats}
        continue

    train = base[["subject_id", "AGE"] + feats].copy()
    train = train[train[feats].notna().sum(axis=1) >= max(2, int(np.ceil(len(feats) * 0.6)))]
    n = len(train)
    if n < 100:
        metadata[organ] = {"status": "skipped", "reason": f"training n={n} <100", "features": feats}
        continue

    X = train[feats]
    y = train["AGE"].astype(float)
    folds = min(5, max(2, n // 50))
    cv = KFold(n_splits=folds, shuffle=True, random_state=SEED)
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("ridge", RidgeCV(alphas=np.logspace(-3, 3, 25))),
    ])
    oof = cross_val_predict(model, X, y, cv=cv, n_jobs=1)
    raw_gap = oof - y.to_numpy()

    # Correct age-gap bias using OOF baseline predictions only.
    slope, intercept = np.polyfit(y.to_numpy(), raw_gap, 1)
    corrected = raw_gap - (intercept + slope * y.to_numpy())

    tmp = pd.DataFrame({
        "subject_id": train["subject_id"].values,
        "organ": organ,
        "AGE": y.values,
        "predicted_age_oof": oof,
        "raw_age_gap_oof": raw_gap,
        "age_acceleration_oof": corrected,
    })
    baseline_oof.append(tmp)

    model.fit(X, y)
    joblib.dump(model, OUT / f"{organ}_organ_age_model.joblib")

    apply = panel[["subject_id", "visit_index", "time_years", "AGE"] + feats].copy()
    valid = apply["AGE"].notna() & (apply[feats].notna().sum(axis=1) >= max(2, int(np.ceil(len(feats) * 0.6))))
    apply = apply.loc[valid].copy()
    pred = model.predict(apply[feats])
    rgap = pred - apply["AGE"].astype(float).to_numpy()
    accel = rgap - (intercept + slope * apply["AGE"].astype(float).to_numpy())

    apply["organ"] = organ
    apply["predicted_age"] = pred
    apply["raw_age_gap"] = rgap
    apply["age_acceleration"] = accel
    all_preds.append(apply[[
        "subject_id", "visit_index", "time_years", "AGE", "organ",
        "predicted_age", "raw_age_gap", "age_acceleration"
    ]])

    rmse = float(np.sqrt(np.mean((oof - y.to_numpy()) ** 2)))
    r = float(np.corrcoef(oof, y.to_numpy())[0, 1])
    metadata[organ] = {
        "status": "ok",
        "n_train": int(n),
        "features": feats,
        "oof_rmse": rmse,
        "oof_age_correlation": r,
        "gap_bias_slope": float(slope),
        "gap_bias_intercept": float(intercept),
    }

if not all_preds:
    raise RuntimeError("No organ-age model could be fit. Check Stage 1 variable coverage.")

preds = pd.concat(all_preds, ignore_index=True)
oof_df = pd.concat(baseline_oof, ignore_index=True)
preds.to_csv(OUT / "ORGAN_AGE_LONG.tsv.gz", sep="\t", index=False, compression="gzip")
oof_df.to_csv(OUT / "BASELINE_OOF_ORGAN_AGE.tsv.gz", sep="\t", index=False, compression="gzip")
(OUT / "ORGAN_AGE_MODEL_QC.json").write_text(json.dumps(metadata, indent=2))
print(json.dumps(metadata, indent=2))
