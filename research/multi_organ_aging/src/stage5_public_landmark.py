from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from common import bh_fdr, ensure_dir, json_dump, load_config, write_table, zscore


def build_one_outcome(panel: pd.DataFrame, concept: str, cutoff: int) -> pd.DataFrame:
    hist_col = f"{concept}_history"
    if hist_col not in panel.columns:
        return pd.DataFrame()

    d = panel.sort_values(["person_id", "visit_index", "year_offset"]).copy()

    pre = d[pd.to_numeric(d["visit_index"], errors="coerce").le(cutoff)].copy()
    landmark = (
        pre.sort_values(["person_id", "visit_index", "year_offset"])
        .drop_duplicates("person_id", keep="last")
        [["person_id", "year_offset", "age", "sex_male", hist_col]]
        .rename(
            columns={
                "year_offset": "landmark_year_offset",
                "age": "landmark_age",
                hist_col: "landmark_history",
            }
        )
    )

    post = d[pd.to_numeric(d["visit_index"], errors="coerce").gt(cutoff)].copy()
    post = post.merge(
        landmark[["person_id", "landmark_year_offset", "landmark_history"]],
        on="person_id",
        how="inner",
    )

    # Incident-risk set: documented disease-free through landmark.
    post = post[post["landmark_history"].eq(0)].copy()
    if post.empty:
        return pd.DataFrame()

    rows = []
    for pid, g in post.groupby("person_id", sort=False):
        g = g.sort_values("year_offset")
        lm = float(g["landmark_year_offset"].iloc[0])

        observed = g[g[hist_col].notna()].copy()
        if observed.empty:
            continue

        events = observed[observed[hist_col].eq(1)]
        if not events.empty:
            event = 1
            end = float(events["year_offset"].iloc[0])
        else:
            event = 0
            end = float(observed["year_offset"].max())

        duration = end - lm
        if not np.isfinite(duration) or duration <= 0:
            continue

        rows.append(
            {
                "person_id": pid,
                f"{concept}_event": event,
                f"{concept}_time": duration,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    return landmark.merge(out, on="person_id", how="inner")


def fit_cox(
    df: pd.DataFrame,
    duration: str,
    event: str,
    exposure: str,
    covars: list[str],
) -> dict:
    try:
        from lifelines import CoxPHFitter
    except Exception as exc:
        return {"status": f"lifelines_unavailable:{exc}"}

    use = [duration, event, exposure] + [c for c in covars if c in df.columns]
    x = df[use].copy()
    for c in use:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna()

    events = int(x[event].sum()) if len(x) else 0
    if len(x) < 100 or events < 20 or x[exposure].std(ddof=0) == 0:
        return {"status": "insufficient_data", "n": int(len(x)), "events": events}

    x[exposure] = zscore(x[exposure])

    model = CoxPHFitter(penalizer=0.001)
    model.fit(x, duration_col=duration, event_col=event, show_progress=False)
    row = model.summary.loc[exposure]

    return {
        "status": "ok",
        "n": int(len(x)),
        "events": events,
        "coef_per_sd": float(row["coef"]),
        "hr_per_sd": float(np.exp(row["coef"])),
        "ci95_low": float(np.exp(row["coef lower 95%"])),
        "ci95_high": float(np.exp(row["coef upper 95%"])),
        "p": float(row["p"]),
        "concordance_index": float(model.concordance_index_),
        "partial_aic": float(model.AIC_partial_),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Public KoGES landmark outcome prototype; workflow QA only."
    )
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.out_dir or cfg["paths"]["out_dir"])
    out = ensure_dir(root / "stage5_public_landmark")

    lm = cfg["landmark"]
    cutoff = int(lm["exposure_max_visit_index"])

    panel = pd.read_csv(
        root / "stage1_longitudinal" / "LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz",
        sep="\t",
        compression="infer",
        low_memory=False,
    )
    expo = pd.read_csv(
        root / "stage3b_landmark_pace" / "LANDMARK_SUBJECT_MULTI_ORGAN_SUMMARY.tsv.gz",
        sep="\t",
        compression="infer",
        low_memory=False,
    )

    outcomes = {}
    event_rows = []
    for concept in lm.get("prototype_outcomes", []):
        y = build_one_outcome(panel, concept, cutoff)
        if y.empty:
            continue
        outcomes[concept] = y
        event_col = f"{concept}_event"
        event_rows.append(
            {
                "outcome": concept,
                "at_risk_with_followup": int(len(y)),
                "events": int(y[event_col].sum()),
                "event_fraction": float(y[event_col].mean()),
            }
        )

    event_df = pd.DataFrame(event_rows)
    write_table(event_df, out / "PUBLIC_LANDMARK_EVENT_COUNTS.tsv")

    if not outcomes:
        info = {
            "status": "not_run",
            "reason": "no_prototype_outcome_available",
            "note": "Public training data are workflow QA only.",
        }
        json_dump(info, out / "STAGE5_PUBLIC_LANDMARK_SUMMARY.json")
        print(info)
        return 0

    merged_outcomes = None
    for concept, y in outcomes.items():
        cols = ["person_id", f"{concept}_event", f"{concept}_time"]
        if merged_outcomes is None:
            merged_outcomes = y[cols].copy()
        else:
            merged_outcomes = merged_outcomes.merge(y[cols], on="person_id", how="outer")

    analysis = expo.merge(merged_outcomes, on="person_id", how="left")

    # Landmark age/sex are taken from the exposure cutoff visit.
    landmark_cov = (
        panel[pd.to_numeric(panel["visit_index"], errors="coerce").le(cutoff)]
        .sort_values(["person_id", "visit_index", "year_offset"])
        .drop_duplicates("person_id", keep="last")
        [["person_id", "age", "sex_male", "year_offset"]]
        .rename(
            columns={
                "age": "landmark_age",
                "year_offset": "landmark_year_offset",
            }
        )
    )
    analysis = analysis.merge(landmark_cov, on="person_id", how="left")
    write_table(analysis, out / "PUBLIC_LANDMARK_ANALYSIS_DATA.tsv.gz")

    primary_map = {
        "htn_dx": "cardiovascular_pace_z",
        "t2d_dx": "metabolic_pace_z",
    }
    exploratory = [
        "multi_organ_landmark_pace_z",
        "discordance_sd",
    ]

    rows = []
    for concept in outcomes:
        event = f"{concept}_event"
        duration = f"{concept}_time"
        exposures = []
        primary = primary_map.get(concept)
        if primary in analysis.columns:
            exposures.append((primary, "primary"))
        for x in exploratory:
            if x in analysis.columns and x != primary:
                exposures.append((x, "exploratory"))

        for exposure, role in exposures:
            r = fit_cox(
                analysis,
                duration,
                event,
                exposure,
                ["landmark_age", "sex_male"],
            )
            r.update(
                {
                    "outcome": concept,
                    "exposure": exposure,
                    "analysis_role": role,
                    "model_spec": "age_sex",
                    "event_col": event,
                    "time_col": duration,
                }
            )
            rows.append(r)

            # For the prespecified organ-specific exposure, test whether pace
            # adds signal beyond the person's starting organ-age state.
            if role == "primary":
                organ = exposure.removesuffix("_pace_z")
                baseline_state = f"{organ}_baseline_accel_z"
                if baseline_state in analysis.columns:
                    r2 = fit_cox(
                        analysis,
                        duration,
                        event,
                        exposure,
                        ["landmark_age", "sex_male", baseline_state],
                    )
                    r2.update(
                        {
                            "outcome": concept,
                            "exposure": exposure,
                            "analysis_role": "primary_sensitivity",
                            "model_spec": f"age_sex_plus_{baseline_state}",
                            "event_col": event,
                            "time_col": duration,
                        }
                    )
                    rows.append(r2)

    res = pd.DataFrame(rows)
    if not res.empty and "p" in res.columns:
        res["q_fdr_within_role"] = np.nan
        for role, idx in res.groupby("analysis_role").groups.items():
            ok_idx = [i for i in idx if pd.notna(res.loc[i, "p"])]
            if ok_idx:
                res.loc[ok_idx, "q_fdr_within_role"] = bh_fdr(
                    res.loc[ok_idx, "p"].to_numpy()
                )

    write_table(res, out / "PUBLIC_LANDMARK_ASSOCIATIONS.tsv")

    model_counts = []
    for concept in outcomes:
        event = f"{concept}_event"
        time = f"{concept}_time"
        if event in analysis.columns and time in analysis.columns:
            d = analysis[[event, time]].dropna()
            model_counts.append({
                "outcome": concept,
                "landmark_pace_eligible_with_followup": int(len(d)),
                "events_in_landmark_pace_eligible": int(d[event].sum()),
            })
    write_table(
        pd.DataFrame(model_counts),
        out / "PUBLIC_LANDMARK_MODEL_ELIGIBLE_COUNTS.tsv",
    )

    info = {
        "status": "ok",
        "exposure_window": f"visit_index 0..{cutoff}",
        "outcome_window": f"visit_index > {cutoff}",
        "subjects_with_landmark_pace": int(expo["person_id"].nunique()),
        "outcomes": event_rows,
        "model_eligible_counts": model_counts,
        "models_tested": int(len(res)),
        "note": (
            "Public KoGES training data are educational/prototype data. "
            "Effect estimates are workflow QA only and must not be reported as thesis inference."
        ),
    }
    json_dump(info, out / "STAGE5_PUBLIC_LANDMARK_SUMMARY.json")
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
