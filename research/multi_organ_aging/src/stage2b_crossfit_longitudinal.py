from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, KFold

from common import ensure_dir, json_dump, load_config, safe_corr, write_table
from stage2_train_organ_clocks import (
    apply_gap_residualizer,
    apply_standardizer,
    fit_gap_residualizer,
    fit_standardizer,
    healthy_reference_mask,
    make_model,
)


def inner_oof_predictions(best_estimator, x: pd.DataFrame, y: pd.Series, groups: pd.Series) -> pd.Series:
    n_splits = min(3, int(groups.nunique()))
    pred = pd.Series(np.nan, index=x.index, dtype=float)

    if n_splits < 2:
        model = clone(best_estimator)
        model.fit(x, y)
        pred.loc[:] = model.predict(x)
        return pred

    cv = GroupKFold(n_splits=n_splits)
    for tr, te in cv.split(x, y, groups):
        model = clone(best_estimator)
        model.fit(x.iloc[tr], y.iloc[tr])
        pred.iloc[te] = model.predict(x.iloc[te])

    return pred


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Subject-level cross-fitted longitudinal organ-age scoring."
    )
    ap.add_argument("--config", required=True)
    ap.add_argument("--panel", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.out_dir or cfg["paths"]["out_dir"])
    panel_path = Path(
        args.panel
        or root / "stage1_longitudinal" / "LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz"
    )
    out = ensure_dir(root / "stage2b_crossfit")

    df = pd.read_csv(panel_path, sep="\t", compression="infer", low_memory=False)
    df["person_id"] = df["person_id"].astype(str)

    baseline = (
        df.sort_values(["person_id", "visit_index", "year_offset"])
        .drop_duplicates("person_id", keep="first")
        .copy()
    )

    all_subjects = np.array(sorted(df["person_id"].dropna().unique().tolist()))
    n_splits = min(int(cfg["clock"]["group_folds"]), len(all_subjects))
    splitter = KFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=int(cfg["clock"]["random_state"]),
    )

    subject_fold = {}
    fold_subjects = []
    for fold, (_, te) in enumerate(splitter.split(all_subjects), start=1):
        ids = set(all_subjects[te].tolist())
        fold_subjects.append((fold, ids))
        for pid in ids:
            subject_fold[pid] = fold

    score_frames = []
    fold_rows = []
    performance_rows = []

    for organ, spec in cfg["organs"].items():
        candidates = [c for c in spec["features"] if c in baseline.columns]
        keep = [
            c
            for c in candidates
            if baseline[c].notna().mean()
            >= float(cfg["clock"]["min_nonmissing_fraction"])
        ]

        if len(keep) < int(spec["min_features"]):
            performance_rows.append(
                {
                    "organ": organ,
                    "status": "insufficient_features",
                    "features": ",".join(keep),
                }
            )
            print(f"[SKIP] {organ}: insufficient_features")
            continue

        ref_mask = healthy_reference_mask(baseline, cfg)
        ref = baseline.loc[
            ref_mask & baseline["age"].notna() & baseline["person_id"].notna()
        ].copy()

        if (
            len(ref) < int(cfg["clock"]["min_rows"])
            or ref["person_id"].nunique() < int(cfg["clock"]["min_subjects"])
        ):
            performance_rows.append(
                {
                    "organ": organ,
                    "status": "insufficient_reference_rows",
                    "features": ",".join(keep),
                    "n_reference_rows": int(len(ref)),
                    "n_reference_subjects": int(ref["person_id"].nunique()),
                }
            )
            print(f"[SKIP] {organ}: insufficient_reference_rows")
            continue

        ref_ids = set(ref["person_id"].astype(str))
        heldout_ref_rows = []

        for fold, test_ids in fold_subjects:
            train_ref = ref[~ref["person_id"].isin(test_ids)].copy()
            test_long = df[df["person_id"].isin(test_ids)].copy()

            if len(train_ref) < int(cfg["clock"]["min_subjects"]):
                raise RuntimeError(
                    f"{organ} fold {fold}: too few reference subjects after holdout"
                )

            xtr = train_ref[keep]
            ytr = train_ref["age"].astype(float)
            gtr = train_ref["person_id"].astype(str)

            tuned = make_model(cfg)
            tuned.fit(xtr, ytr)
            best_estimator = tuned.best_estimator_

            # Fit age-gap residualization and scaling using training participants
            # only. Inner OOF predictions avoid fitting the correction on purely
            # in-sample age predictions.
            inner_pred = inner_oof_predictions(best_estimator, xtr, ytr, gtr)
            inner_gap = inner_pred - ytr
            gap_beta = fit_gap_residualizer(
                inner_gap,
                ytr,
                train_ref["sex_male"],
            )
            inner_accel = apply_gap_residualizer(
                inner_gap,
                ytr,
                train_ref["sex_male"],
                gap_beta,
            )
            accel_mean, accel_sd = fit_standardizer(inner_accel)

            cols = [
                "person_id",
                "wave",
                "visit_index",
                "year_offset",
                "age",
                "sex_male",
            ] + keep
            scored = test_long[cols].copy()
            scored["organ"] = organ
            scored["outer_fold"] = fold
            scored["predicted_age"] = best_estimator.predict(scored[keep])
            scored["raw_age_gap"] = scored["predicted_age"] - scored["age"]
            scored["age_acceleration"] = apply_gap_residualizer(
                scored["raw_age_gap"],
                scored["age"],
                scored["sex_male"],
                gap_beta,
            )
            scored["age_acceleration_z"] = apply_standardizer(
                scored["age_acceleration"],
                accel_mean,
                accel_sd,
            )
            scored["crossfit_subject_holdout"] = 1
            score_frames.append(scored)

            test_ref_ids = test_ids & ref_ids
            if test_ref_ids:
                btest = scored[
                    scored["person_id"].isin(test_ref_ids)
                    & scored["visit_index"].eq(0)
                ].copy()
                btest["reference_subject"] = 1
                heldout_ref_rows.append(btest)

            fold_rows.append(
                {
                    "organ": organ,
                    "fold": fold,
                    "n_train_reference": int(len(train_ref)),
                    "n_test_subjects": int(len(test_ids)),
                    "n_test_reference": int(len(test_ref_ids)),
                    "best_alpha": float(tuned.best_params_["enet__alpha"]),
                    "best_l1_ratio": float(tuned.best_params_["enet__l1_ratio"]),
                    "gap_beta_intercept": (
                        float(gap_beta[0]) if gap_beta is not None else np.nan
                    ),
                    "gap_beta_age": (
                        float(gap_beta[1]) if gap_beta is not None else np.nan
                    ),
                    "gap_beta_sex": (
                        float(gap_beta[2]) if gap_beta is not None else np.nan
                    ),
                    "accel_reference_mean": float(accel_mean),
                    "accel_reference_sd": float(accel_sd),
                }
            )

        if heldout_ref_rows:
            oof = pd.concat(heldout_ref_rows, ignore_index=True)
            y = pd.to_numeric(oof["age"], errors="coerce")
            pred = pd.to_numeric(oof["predicted_age"], errors="coerce")
            raw_gap = pd.to_numeric(oof["raw_age_gap"], errors="coerce")
            accel = pd.to_numeric(oof["age_acceleration"], errors="coerce")

            performance_rows.append(
                {
                    "organ": organ,
                    "status": "ok",
                    "features": ",".join(keep),
                    "n_reference_subjects": int(oof["person_id"].nunique()),
                    "crossfit_oof_mae": float(mean_absolute_error(y, pred)),
                    "crossfit_oof_r2": float(r2_score(y, pred)),
                    "corr_gap_age_before": safe_corr(raw_gap, y),
                    "corr_gap_age_after": safe_corr(accel, y),
                    "scoring_scope": "subject-level holdout; all visits scored by a model not trained on that subject",
                }
            )
            print(
                f"[OK] {organ}: crossfit reference_n={oof['person_id'].nunique()} "
                f"MAE={mean_absolute_error(y, pred):.3f} "
                f"R2={r2_score(y, pred):.3f}"
            )

    if not score_frames:
        raise SystemExit("No organ could be cross-fit.")

    scores = pd.concat(score_frames, ignore_index=True)
    scores = scores.sort_values(
        ["person_id", "organ", "visit_index", "year_offset"]
    ).reset_index(drop=True)

    # Every scored participant must belong to exactly one outer fold per organ.
    fold_check = (
        scores.groupby(["person_id", "organ"])["outer_fold"]
        .nunique()
        .reset_index(name="n_outer_folds")
    )
    if not fold_check["n_outer_folds"].eq(1).all():
        raise RuntimeError("Cross-fit leakage guard failed: participant appears in >1 outer fold.")

    write_table(scores, out / "ORGAN_AGE_SCORES_LONG_CROSSFIT.tsv.gz")
    write_table(pd.DataFrame(fold_rows), out / "CROSSFIT_FOLD_METADATA.tsv")
    write_table(pd.DataFrame(performance_rows), out / "CROSSFIT_CLOCK_PERFORMANCE.tsv")
    write_table(fold_check, out / "CROSSFIT_SUBJECT_FOLD_CHECK.tsv")

    info = {
        "status": "ok",
        "subjects": int(scores["person_id"].nunique()),
        "organs": sorted(scores["organ"].unique().tolist()),
        "rows": int(len(scores)),
        "outer_folds": int(n_splits),
        "subject_holdout_complete": bool(
            fold_check["n_outer_folds"].eq(1).all()
        ),
        "primary_use": (
            "Use this file for longitudinal pace and outcome analyses in the "
            "training cohort. Final-model scores are retained for deployment/external scoring."
        ),
    }
    json_dump(info, out / "STAGE2B_CROSSFIT_SUMMARY.json")
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
