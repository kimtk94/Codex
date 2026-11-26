from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from common import ensure_dir, json_dump, load_config, write_table, zscore


PRIMARY_MAP = {
    "htn_dx": "cardiovascular_pace_z",
    "t2d_dx": "metabolic_pace_z",
}


def prepare_joint_data(
    analysis: pd.DataFrame,
    outcome: str,
    pace_col: str,
) -> tuple[pd.DataFrame, str, str, str]:
    event = f"{outcome}_event"
    duration = f"{outcome}_time"
    organ = pace_col.removesuffix("_pace_z")
    baseline = f"{organ}_baseline_accel_z"

    cols = [
        "person_id",
        duration,
        event,
        pace_col,
        baseline,
        "landmark_age",
        "sex_male",
    ]
    missing = [c for c in cols if c not in analysis.columns]
    if missing:
        raise ValueError(f"{outcome}: missing columns {missing}")

    d = analysis[cols].copy()
    for c in cols:
        if c != "person_id":
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna()
    d = d[d[duration].gt(0)].copy()

    return d, event, duration, baseline


def orthogonalize_pace(d: pd.DataFrame, pace: str, baseline: str) -> pd.Series:
    x = d[baseline].to_numpy(float)
    y = d[pace].to_numpy(float)
    X = np.column_stack([np.ones(len(d)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    return pd.Series(resid, index=d.index, dtype=float)


def fit_joint(
    d: pd.DataFrame,
    event: str,
    duration: str,
    pace: str,
    baseline: str,
    orthogonalized: bool = False,
):
    from lifelines import CoxPHFitter

    x = d[[duration, event, pace, baseline, "landmark_age", "sex_male"]].copy()

    pace_name = pace
    if orthogonalized:
        x["orthogonalized_pace"] = orthogonalize_pace(x, pace, baseline)
        x = x.drop(columns=[pace])
        pace_name = "orthogonalized_pace"

    x[pace_name] = zscore(x[pace_name])
    x[baseline] = zscore(x[baseline])

    model = CoxPHFitter(penalizer=0.001)
    model.fit(x, duration_col=duration, event_col=event, show_progress=False)

    row = model.summary.loc[pace_name]
    return model, {
        "coef_per_sd": float(row["coef"]),
        "hr_per_sd": float(np.exp(row["coef"])),
        "ci95_low": float(np.exp(row["coef lower 95%"])),
        "ci95_high": float(np.exp(row["coef upper 95%"])),
        "p": float(row["p"]),
        "concordance_index": float(model.concordance_index_),
        "partial_aic": float(model.AIC_partial_),
        "log_likelihood": float(model.log_likelihood_),
        "pace_variable_in_model": pace_name,
    }


def fit_baseline_only(
    d: pd.DataFrame,
    event: str,
    duration: str,
    baseline: str,
):
    from lifelines import CoxPHFitter

    x = d[[duration, event, baseline, "landmark_age", "sex_male"]].copy()
    x[baseline] = zscore(x[baseline])

    model = CoxPHFitter(penalizer=0.001)
    model.fit(x, duration_col=duration, event_col=event, show_progress=False)
    return model


def proportional_hazards_rows(
    model,
    d: pd.DataFrame,
    event: str,
    duration: str,
    pace: str,
    baseline: str,
    outcome: str,
) -> list[dict]:
    from lifelines.statistics import proportional_hazard_test

    x = d[[duration, event, pace, baseline, "landmark_age", "sex_male"]].copy()
    x[pace] = zscore(x[pace])
    x[baseline] = zscore(x[baseline])

    test = proportional_hazard_test(
        model,
        x,
        time_transform="rank",
    )

    rows = []
    for variable in test.summary.index:
        row = test.summary.loc[variable]
        rows.append(
            {
                "outcome": outcome,
                "variable": variable,
                "test_statistic": float(row["test_statistic"]),
                "p_ph": float(row["p"]),
                "passes_p_0_05": bool(float(row["p"]) >= 0.05),
            }
        )
    return rows


def bootstrap_one(
    d: pd.DataFrame,
    event: str,
    duration: str,
    pace: str,
    baseline: str,
    reps: int,
    seed: int,
    outcome: str,
) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    rows = []
    n = len(d)

    for rep in range(1, reps + 1):
        take = rng.integers(0, n, size=n)
        b = d.iloc[take].reset_index(drop=True)

        if b[event].sum() < 10 or b[event].nunique() < 2:
            rows.append(
                {
                    "outcome": outcome,
                    "rep": rep,
                    "status": "insufficient_events",
                }
            )
            continue

        try:
            base_model = fit_baseline_only(
                b,
                event,
                duration,
                baseline,
            )
            joint_model, joint = fit_joint(
                b,
                event,
                duration,
                pace,
                baseline,
                orthogonalized=False,
            )

            rows.append(
                {
                    "outcome": outcome,
                    "rep": rep,
                    "status": "ok",
                    "pace_hr_per_sd": joint["hr_per_sd"],
                    "pace_coef_per_sd": joint["coef_per_sd"],
                    "joint_c_index": joint["concordance_index"],
                    "baseline_c_index": float(base_model.concordance_index_),
                    "delta_c_index": (
                        float(joint_model.concordance_index_)
                        - float(base_model.concordance_index_)
                    ),
                    "joint_partial_aic": float(joint_model.AIC_partial_),
                    "baseline_partial_aic": float(base_model.AIC_partial_),
                    "delta_aic": (
                        float(joint_model.AIC_partial_)
                        - float(base_model.AIC_partial_)
                    ),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "outcome": outcome,
                    "rep": rep,
                    "status": f"fit_error:{type(exc).__name__}",
                }
            )

    boot = pd.DataFrame(rows)
    ok = boot[boot["status"].eq("ok")].copy()

    if ok.empty:
        summary = {
            "outcome": outcome,
            "bootstrap_reps_requested": reps,
            "bootstrap_reps_ok": 0,
        }
        return boot, summary

    def q(col: str, prob: float) -> float:
        return float(pd.to_numeric(ok[col], errors="coerce").quantile(prob))

    summary = {
        "outcome": outcome,
        "bootstrap_reps_requested": reps,
        "bootstrap_reps_ok": int(len(ok)),
        "hr_median": q("pace_hr_per_sd", 0.50),
        "hr_ci025": q("pace_hr_per_sd", 0.025),
        "hr_ci975": q("pace_hr_per_sd", 0.975),
        "fraction_hr_gt_1": float((ok["pace_hr_per_sd"] > 1).mean()),
        "delta_c_index_median": q("delta_c_index", 0.50),
        "delta_c_index_ci025": q("delta_c_index", 0.025),
        "delta_c_index_ci975": q("delta_c_index", 0.975),
        "fraction_delta_c_gt_0": float((ok["delta_c_index"] > 0).mean()),
        "delta_aic_median": q("delta_aic", 0.50),
        "delta_aic_ci025": q("delta_aic", 0.025),
        "delta_aic_ci975": q("delta_aic", 0.975),
        "fraction_delta_aic_lt_0": float((ok["delta_aic"] < 0).mean()),
    }
    return boot, summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Robustness checks for cross-fitted landmark pace associations."
    )
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--bootstrap-reps", type=int, default=500)
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.out_dir or cfg["paths"]["out_dir"])
    src = root / "stage5_public_landmark" / "PUBLIC_LANDMARK_ANALYSIS_DATA.tsv.gz"
    out = ensure_dir(root / "stage5b_robustness")

    if not src.exists():
        raise SystemExit(f"Missing Stage 5 landmark analysis data: {src}")

    analysis = pd.read_csv(src, sep="\t", compression="infer", low_memory=False)

    orth_rows = []
    ph_rows = []
    boot_frames = []
    boot_summaries = []

    for i, (outcome, pace) in enumerate(PRIMARY_MAP.items()):
        d, event, duration, baseline = prepare_joint_data(
            analysis,
            outcome,
            pace,
        )
        events = int(d[event].sum())
        if len(d) < 100 or events < 20:
            print(f"[SKIP] {outcome}: n={len(d)} events={events}")
            continue

        joint_model, joint = fit_joint(
            d,
            event,
            duration,
            pace,
            baseline,
            orthogonalized=False,
        )
        _, orth = fit_joint(
            d,
            event,
            duration,
            pace,
            baseline,
            orthogonalized=True,
        )

        corr = float(d[pace].corr(d[baseline]))
        orth_resid = orthogonalize_pace(d, pace, baseline)

        orth_rows.append(
            {
                "outcome": outcome,
                "n": int(len(d)),
                "events": events,
                "pace": pace,
                "baseline_state": baseline,
                "corr_pace_baseline": corr,
                "joint_hr_per_sd": joint["hr_per_sd"],
                "joint_ci95_low": joint["ci95_low"],
                "joint_ci95_high": joint["ci95_high"],
                "joint_p": joint["p"],
                "orthogonalized_hr_per_sd": orth["hr_per_sd"],
                "orthogonalized_ci95_low": orth["ci95_low"],
                "orthogonalized_ci95_high": orth["ci95_high"],
                "orthogonalized_p": orth["p"],
                "corr_orthogonalized_pace_baseline": float(
                    pd.Series(orth_resid, index=d.index).corr(d[baseline])
                ),
            }
        )

        ph_rows.extend(
            proportional_hazards_rows(
                joint_model,
                d,
                event,
                duration,
                pace,
                baseline,
                outcome,
            )
        )

        boot, boot_summary = bootstrap_one(
            d,
            event,
            duration,
            pace,
            baseline,
            reps=int(args.bootstrap_reps),
            seed=int(cfg["clock"]["random_state"]) + i * 100003,
            outcome=outcome,
        )
        boot_frames.append(boot)
        boot_summaries.append(boot_summary)

        print(
            f"[OK] {outcome}: n={len(d)} events={events} "
            f"joint_HR={joint['hr_per_sd']:.3f} "
            f"orthogonalized_HR={orth['hr_per_sd']:.3f}"
        )

    orth_df = pd.DataFrame(orth_rows)
    ph_df = pd.DataFrame(ph_rows)
    boot_all = (
        pd.concat(boot_frames, ignore_index=True)
        if boot_frames
        else pd.DataFrame()
    )
    boot_summary_df = pd.DataFrame(boot_summaries)

    write_table(
        orth_df,
        out / "ORTHOGONALIZED_PACE_ASSOCIATIONS.tsv",
    )
    write_table(
        ph_df,
        out / "PROPORTIONAL_HAZARDS_TEST.tsv",
    )
    write_table(
        boot_all,
        out / "BOOTSTRAP_REPLICATES.tsv.gz",
    )
    write_table(
        boot_summary_df,
        out / "BOOTSTRAP_SUMMARY.tsv",
    )

    ph_ok = True
    if not ph_df.empty:
        ph_ok = bool(ph_df["p_ph"].ge(0.05).all())

    info = {
        "status": "ok",
        "bootstrap_reps": int(args.bootstrap_reps),
        "outcomes_tested": orth_df["outcome"].tolist() if not orth_df.empty else [],
        "all_joint_model_covariates_pass_ph_p_0_05": ph_ok,
        "interpretation": (
            "Robustness diagnostics only. Public KoGES training data remain "
            "workflow-validation data and are not final thesis inference."
        ),
    }
    json_dump(info, out / "STAGE5B_ROBUSTNESS_SUMMARY.json")
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
