from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from common import ensure_dir, json_dump, load_config, safe_corr, write_table, zscore


def make_model(cfg: dict) -> GridSearchCV:
    pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", RobustScaler()),
            (
                "enet",
                ElasticNet(
                    max_iter=20000,
                    random_state=int(cfg["clock"]["random_state"]),
                ),
            ),
        ]
    )
    grid = {
        "enet__alpha": cfg["clock"]["alphas"],
        "enet__l1_ratio": cfg["clock"]["l1_ratios"],
    }
    return GridSearchCV(pipe, grid, scoring="neg_mean_absolute_error", cv=3, n_jobs=-1)


def residualize_gap(raw_gap: pd.Series, age: pd.Series, sex: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"gap": raw_gap, "age": age, "sex": sex}).dropna()
    if len(frame) < 50:
        return raw_gap
    X = np.column_stack(
        [
            np.ones(len(frame)),
            frame["age"].to_numpy(float),
            frame["sex"].to_numpy(float),
        ]
    )
    y = frame["gap"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    resid = pd.Series(y - fitted, index=frame.index)
    return resid.reindex(raw_gap.index)


def healthy_reference_mask(df: pd.DataFrame, cfg: dict) -> pd.Series:
    lo = float(cfg["clock"]["healthy_reference_age_min"])
    hi = float(cfg["clock"]["healthy_reference_age_max"])
    mask = df["age"].between(lo, hi)
    for col in ["htn_dx", "t2d_dx", "ckd_dx", "cvd_dx"]:
        if col in df.columns and df[col].notna().any():
            mask &= ~(pd.to_numeric(df[col], errors="coerce").fillna(0) > 0)
    return mask


def train_one_organ(
    df: pd.DataFrame,
    organ: str,
    spec: dict,
    cfg: dict,
    model_dir: Path,
):
    candidates = [c for c in spec["features"] if c in df.columns]
    keep = [
        c
        for c in candidates
        if df[c].notna().mean() >= float(cfg["clock"]["min_nonmissing_fraction"])
    ]
    if len(keep) < int(spec["min_features"]):
        return None, {"organ": organ, "status": "insufficient_features", "features": keep}

    required = ["person_id", "age", "sex_male"] + keep
    d = df[required].copy()
    d = d[d["age"].notna() & d["person_id"].notna()]
    ref = healthy_reference_mask(df.loc[d.index], cfg)
    d = d.loc[ref].copy()
    n_subjects = d["person_id"].nunique()

    if len(d) < int(cfg["clock"]["min_rows"]) or n_subjects < int(cfg["clock"]["min_subjects"]):
        return None, {
            "organ": organ,
            "status": "insufficient_reference_rows",
            "n_rows": len(d),
            "n_subjects": n_subjects,
            "features": keep,
        }

    X = d[keep]
    y = d["age"].astype(float)
    groups = d["person_id"].astype(str)
    n_splits = min(int(cfg["clock"]["group_folds"]), int(groups.nunique()))
    if n_splits < 3:
        return None, {"organ": organ, "status": "insufficient_group_folds", "features": keep}

    outer = GroupKFold(n_splits=n_splits)
    pred = pd.Series(np.nan, index=d.index, dtype=float)
    fold_rows = []

    for fold, (tr, te) in enumerate(outer.split(X, y, groups), start=1):
        model = make_model(cfg)
        model.fit(X.iloc[tr], y.iloc[tr])
        p = model.predict(X.iloc[te])
        pred.iloc[te] = p
        fold_rows.append(
            {
                "organ": organ,
                "fold": fold,
                "n_train": len(tr),
                "n_test": len(te),
                "mae": mean_absolute_error(y.iloc[te], p),
                "r2": r2_score(y.iloc[te], p),
                "best_alpha": model.best_params_["enet__alpha"],
                "best_l1_ratio": model.best_params_["enet__l1_ratio"],
            }
        )

    raw_gap = pred - y
    age_accel = residualize_gap(raw_gap, y, d["sex_male"])
    accel_z = zscore(age_accel)

    final_model = make_model(cfg)
    final_model.fit(X, y)
    model_path = model_dir / f"{organ}_elasticnet_clock.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": final_model, "features": keep, "organ": organ}, f)

    scored_ref = d[["person_id", "age", "sex_male"]].copy()
    scored_ref["organ"] = organ
    scored_ref["predicted_age_oof"] = pred
    scored_ref["raw_age_gap_oof"] = raw_gap
    scored_ref["age_acceleration_oof"] = age_accel
    scored_ref["age_acceleration_z_oof"] = accel_z

    meta = {
        "organ": organ,
        "status": "ok",
        "features": ",".join(keep),
        "n_rows": int(len(d)),
        "n_subjects": int(n_subjects),
        "oof_mae": float(mean_absolute_error(y, pred)),
        "oof_r2": float(r2_score(y, pred)),
        "corr_gap_age_before": safe_corr(raw_gap, y),
        "corr_gap_age_after": safe_corr(age_accel, y),
        "model_path": str(model_path),
    }
    return scored_ref, meta, pd.DataFrame(fold_rows), final_model, keep


def apply_final_model(
    all_df: pd.DataFrame,
    organ: str,
    model,
    features: list[str],
) -> pd.DataFrame:
    eligible = all_df["age"].notna() & all_df["person_id"].notna()
    cols = ["person_id", "wave", "visit_index", "year_offset", "age", "sex_male"] + features
    d = all_df.loc[eligible, cols].copy()
    d["organ"] = organ
    d["predicted_age"] = model.predict(d[features])
    d["raw_age_gap"] = d["predicted_age"] - d["age"]
    d["age_acceleration"] = residualize_gap(d["raw_age_gap"], d["age"], d["sex_male"])
    d["age_acceleration_z"] = zscore(d["age_acceleration"])
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="Train leakage-aware organ-specific aging clocks.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--panel", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_root = Path(args.out_dir or cfg["paths"]["out_dir"])
    panel_path = Path(
        args.panel
        or out_root / "stage1_longitudinal" / "LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz"
    )
    out = ensure_dir(out_root / "stage2_clocks")
    model_dir = ensure_dir(Path(cfg["paths"].get("model_dir", out_root / "models")))

    df = pd.read_csv(panel_path, sep="\t", compression="infer", low_memory=False)
    all_scores = []
    refs = []
    meta_rows = []
    fold_frames = []

    for organ, spec in cfg["organs"].items():
        result = train_one_organ(df, organ, spec, cfg, model_dir)
        if result[0] is None:
            meta_rows.append(result[1])
            print(f"[SKIP] {organ}: {result[1]['status']}")
            continue
        ref_score, meta, fold_df, final_model, features = result
        refs.append(ref_score)
        meta_rows.append(meta)
        fold_frames.append(fold_df)
        all_scores.append(apply_final_model(df, organ, final_model, features))
        print(f"[OK] {organ}: n={meta['n_rows']} OOF_MAE={meta['oof_mae']:.3f}")

    if not all_scores:
        raise SystemExit("No organ clock was trainable. Review Stage 0/1 variable mapping.")

    scores = pd.concat(all_scores, ignore_index=True)
    ref_scores = pd.concat(refs, ignore_index=True)
    meta_df = pd.DataFrame(meta_rows)
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()

    write_table(scores, out / "ORGAN_AGE_SCORES_LONG.tsv.gz")
    write_table(ref_scores, out / "ORGAN_CLOCK_OOF_REFERENCE.tsv.gz")
    write_table(meta_df, out / "ORGAN_CLOCK_PERFORMANCE.tsv")
    write_table(folds, out / "ORGAN_CLOCK_CV_FOLDS.tsv")

    summary = {
        "trained_organs": meta_df.loc[meta_df["status"].eq("ok"), "organ"].tolist(),
        "n_trained_organs": int(meta_df["status"].eq("ok").sum()),
        "score_rows": int(len(scores)),
        "warning": "Clock coefficients are not causal effects. OOF performance and age-gap residualization are mandatory QC.",
    }
    json_dump(summary, out / "STAGE2_SUMMARY.json")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
