from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import chi2, norm

from common import ensure_dir, json_dump, load_config, write_table


PRIMARY_MAP = {
    "htn_dx": "cardiovascular_pace_z",
    "t2d_dx": "metabolic_pace_z",
}


def z(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    m = x.mean()
    sd = x.std(ddof=0)
    if not np.isfinite(sd) or sd <= 0:
        return x * np.nan
    return (x - m) / sd


def build_person_period(
    panel: pd.DataFrame,
    subject_level: pd.DataFrame,
    outcome: str,
    cutoff: int,
) -> pd.DataFrame:
    hist = f"{outcome}_history"
    if hist not in panel.columns:
        return pd.DataFrame()

    base = subject_level.copy()
    base["person_id"] = base["person_id"].astype(str)

    d = panel.copy()
    d["person_id"] = d["person_id"].astype(str)
    d = d.sort_values(["person_id", "visit_index", "year_offset"])

    pre = d[pd.to_numeric(d["visit_index"], errors="coerce").le(cutoff)].copy()
    landmark = (
        pre.sort_values(["person_id", "visit_index", "year_offset"])
        .drop_duplicates("person_id", keep="last")
        [["person_id", hist]]
        .rename(columns={hist: "landmark_history"})
    )

    eligible = base.merge(landmark, on="person_id", how="inner")
    eligible = eligible[eligible["landmark_history"].eq(0)].copy()
    eligible_ids = set(eligible["person_id"])

    post = d[
        d["person_id"].isin(eligible_ids)
        & pd.to_numeric(d["visit_index"], errors="coerce").gt(cutoff)
    ].copy()

    rows = []
    for pid, g in post.groupby("person_id", sort=False):
        g = g.sort_values(["visit_index", "year_offset"]).copy()
        subject = eligible[eligible["person_id"].eq(pid)].iloc[0]

        event_seen = False
        for _, row in g.iterrows():
            if event_seen:
                break
            if pd.isna(row[hist]):
                continue

            event = int(float(row[hist]) == 1.0)
            rows.append(
                {
                    **subject.drop(labels=["landmark_history"]).to_dict(),
                    "period_visit_index": int(row["visit_index"]),
                    "period_end_year": float(row["year_offset"]),
                    "event": event,
                }
            )
            if event == 1:
                event_seen = True

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    return out


def fit_cloglog(
    pp: pd.DataFrame,
    outcome: str,
    pace: str,
    baseline: str,
    allow_time_interaction: bool,
) -> tuple[dict, pd.DataFrame]:
    use = pp[
        [
            "person_id",
            "event",
            "period_visit_index",
            pace,
            baseline,
            "landmark_age",
            "sex_male",
        ]
    ].copy()

    for c in ["event", "period_visit_index", pace, baseline, "landmark_age", "sex_male"]:
        use[c] = pd.to_numeric(use[c], errors="coerce")
    use = use.dropna()

    use["pace_z_std"] = z(use[pace])
    use["baseline_z_std"] = z(use[baseline])
    use["age_z_std"] = z(use["landmark_age"])

    if allow_time_interaction:
        formula = (
            "event ~ pace_z_std * C(period_visit_index) + "
            "sex_male * C(period_visit_index) + "
            "baseline_z_std + age_z_std"
        )
        model_label = "cloglog_time_varying_pace_and_sex"
    else:
        formula = (
            "event ~ pace_z_std + C(period_visit_index) + "
            "baseline_z_std + age_z_std + sex_male"
        )
        model_label = "cloglog_constant_pace"

    model = smf.glm(
        formula=formula,
        data=use,
        family=sm.families.Binomial(
            link=sm.families.links.CLogLog()
        ),
    )

    try:
        fit = model.fit(
            cov_type="cluster",
            cov_kwds={"groups": use["person_id"]},
            maxiter=200,
        )
    except Exception:
        fit = model.fit(maxiter=200)

    coef_rows = []
    for term in fit.params.index:
        coef = float(fit.params[term])
        se = float(fit.bse[term])
        p = float(fit.pvalues[term])
        coef_rows.append(
            {
                "outcome": outcome,
                "model": model_label,
                "term": term,
                "coef": coef,
                "exp_coef": float(np.exp(coef)),
                "ci95_low": float(np.exp(coef - 1.96 * se)),
                "ci95_high": float(np.exp(coef + 1.96 * se)),
                "p": p,
            }
        )

    summary = {
        "outcome": outcome,
        "model": model_label,
        "rows": int(len(use)),
        "subjects": int(use["person_id"].nunique()),
        "events": int(use["event"].sum()),
        "aic": float(fit.aic),
        "llf": float(fit.llf),
        "converged": bool(getattr(fit, "converged", True)),
    }

    # If the pace effect is time-varying, report interval-specific effects.
    interval_rows = []
    levels = sorted(use["period_visit_index"].dropna().unique().tolist())
    beta = fit.params
    cov = fit.cov_params()

    for level in levels:
        pace_term = "pace_z_std"
        interaction_candidates = [
            f"pace_z_std:C(period_visit_index)[T.{int(level)}]",
            f"C(period_visit_index)[T.{int(level)}]:pace_z_std",
        ]

        terms = [(pace_term, 1.0)]
        if level != levels[0]:
            found = None
            for cand in interaction_candidates:
                if cand in beta.index:
                    found = cand
                    break
            if found is not None:
                terms.append((found, 1.0))

        names = [t[0] for t in terms]
        weights = np.array([t[1] for t in terms], dtype=float)
        b = beta.loc[names].to_numpy(float)
        V = cov.loc[names, names].to_numpy(float)

        est = float(weights @ b)
        var = float(weights @ V @ weights)
        se = float(np.sqrt(max(var, 0.0)))
        zval = est / se if se > 0 else np.nan
        p = (
            float(2.0 * (1.0 - norm.cdf(abs(zval))))
            if np.isfinite(zval)
            else np.nan
        )

        interval_rows.append(
            {
                "outcome": outcome,
                "model": model_label,
                "period_visit_index": int(level),
                "pace_log_hazard_ratio": est,
                "pace_hazard_ratio": float(np.exp(est)),
                "ci95_low": float(np.exp(est - 1.96 * se)),
                "ci95_high": float(np.exp(est + 1.96 * se)),
                "p": p,
            }
        )

    return summary, pd.DataFrame(coef_rows), pd.DataFrame(interval_rows)


def likelihood_ratio(const_summary: dict, tv_summary: dict) -> dict:
    lr = 2.0 * (tv_summary["llf"] - const_summary["llf"])
    df = 1
    p = float(sm.stats.chisqprob(lr, df)) if hasattr(sm.stats, "chisqprob") else np.nan
    return {
        "outcome": const_summary["outcome"],
        "lr_statistic": float(lr),
        "df": df,
        "p_lr": p,
        "delta_aic_timevarying_minus_constant": float(
            tv_summary["aic"] - const_summary["aic"]
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Discrete-time landmark survival sensitivity using cloglog models."
    )
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.out_dir or cfg["paths"]["out_dir"])
    out = ensure_dir(root / "stage5c_discrete_time")

    panel = pd.read_csv(
        root / "stage1_longitudinal" / "LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz",
        sep="\t",
        compression="infer",
        low_memory=False,
    )
    subj = pd.read_csv(
        root / "stage5_public_landmark" / "PUBLIC_LANDMARK_ANALYSIS_DATA.tsv.gz",
        sep="\t",
        compression="infer",
        low_memory=False,
    )

    cutoff = int(cfg["landmark"]["exposure_max_visit_index"])

    model_rows = []
    coef_frames = []
    interval_frames = []
    lr_rows = []
    pp_frames = []

    for outcome, pace in PRIMARY_MAP.items():
        organ = pace.removesuffix("_pace_z")
        baseline = f"{organ}_baseline_accel_z"

        if pace not in subj.columns or baseline not in subj.columns:
            print(f"[SKIP] {outcome}: missing pace/baseline state")
            continue

        pp = build_person_period(
            panel,
            subj,
            outcome,
            cutoff,
        )
        if pp.empty:
            print(f"[SKIP] {outcome}: no person-period rows")
            continue

        pp["outcome"] = outcome
        pp_frames.append(pp)

        const_summary, const_coef, const_intervals = fit_cloglog(
            pp,
            outcome,
            pace,
            baseline,
            allow_time_interaction=False,
        )
        tv_summary, tv_coef, tv_intervals = fit_cloglog(
            pp,
            outcome,
            pace,
            baseline,
            allow_time_interaction=True,
        )

        model_rows.extend([const_summary, tv_summary])
        coef_frames.extend([const_coef, tv_coef])
        interval_frames.extend([const_intervals, tv_intervals])

        # Compare model AIC directly; the time-varying model adds one interaction
        # term because the public prototype has two post-landmark intervals.
        lr_stat = 2.0 * (
            tv_summary["llf"] - const_summary["llf"]
        )
        extra_df = 2  # pace×interval and sex×interval in the public 2-interval model
        lr_rows.append(
            {
                "outcome": outcome,
                "constant_aic": const_summary["aic"],
                "timevarying_aic": tv_summary["aic"],
                "delta_aic_timevarying_minus_constant": (
                    tv_summary["aic"] - const_summary["aic"]
                ),
                "constant_llf": const_summary["llf"],
                "timevarying_llf": tv_summary["llf"],
                "lr_statistic": lr_stat,
                "lr_df": extra_df,
                "lr_p": float(chi2.sf(lr_stat, extra_df)),
                "preferred_by_aic": (
                    "constant"
                    if const_summary["aic"] <= tv_summary["aic"]
                    else "time_varying"
                ),
            }
        )

        print(
            f"[OK] {outcome}: subjects={pp.person_id.nunique()} "
            f"rows={len(pp)} events={int(pp.event.sum())} "
            f"constant_AIC={const_summary['aic']:.2f} "
            f"timevarying_AIC={tv_summary['aic']:.2f}"
        )

    if not model_rows:
        raise SystemExit("No discrete-time model was fitted.")

    pp_all = pd.concat(pp_frames, ignore_index=True)
    coef_all = pd.concat(coef_frames, ignore_index=True)
    interval_all = pd.concat(interval_frames, ignore_index=True)
    model_df = pd.DataFrame(model_rows)
    lr_df = pd.DataFrame(lr_rows)

    write_table(
        pp_all,
        out / "PERSON_PERIOD_DATA.tsv.gz",
    )
    write_table(
        model_df,
        out / "DISCRETE_TIME_MODEL_SUMMARY.tsv",
    )
    write_table(
        coef_all,
        out / "DISCRETE_TIME_COEFFICIENTS.tsv",
    )
    write_table(
        interval_all,
        out / "DISCRETE_TIME_INTERVAL_EFFECTS.tsv",
    )
    write_table(
        lr_df,
        out / "DISCRETE_TIME_TIMEVARIATION_COMPARISON.tsv",
    )

    info = {
        "status": "ok",
        "cutoff_visit_index": cutoff,
        "outcomes": sorted(model_df["outcome"].unique().tolist()),
        "models": sorted(model_df["model"].unique().tolist()),
        "interpretation": (
            "Discrete-time cloglog is a sensitivity analysis for interval-observed "
            "incident diagnoses. Time-varying pace models should be preferred over "
            "a single Cox HR if proportional hazards are not supported."
        ),
    }
    json_dump(info, out / "STAGE5C_DISCRETE_TIME_SUMMARY.json")
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
