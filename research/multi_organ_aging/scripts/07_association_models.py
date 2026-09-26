#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

PATTERNS = Path("/srv/is-analysis/results/multi_organ_aging/stage4_patterns/MULTI_ORGAN_AGING_PATTERNS.tsv.gz")
OUTCOMES = Path("/srv/is-analysis/results/multi_organ_aging/stage5_outcomes/LONGITUDINAL_OUTCOMES.tsv.gz")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage6_association")


def sex_numeric(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.strip().str.upper()
    mapped = raw.map({
        "M": 1, "MALE": 1, "1": 1,
        "F": 0, "FEMALE": 0, "2": 0, "0": 0,
    })
    numeric = pd.to_numeric(s, errors="coerce")
    return mapped.fillna(numeric)


OUT.mkdir(parents=True, exist_ok=True)
pat = pd.read_csv(PATTERNS, sep="\t")
outc = pd.read_csv(OUTCOMES, sep="\t")
df = pat.merge(outc, on="subject_id", how="inner")
df["sex_numeric"] = sex_numeric(df["baseline_SEX"])

exposures = [
    c for c in df.columns
    if c.endswith("_pace_z")
    or c in {
        "mean_aging_z", "max_aging_z", "organ_discordance_z",
        "accelerated_organ_count", "aging_pc1", "aging_pc2"
    }
]
binary_outcomes = [
    c for c in df.columns
    if c.startswith("incident_") and not c.endswith("_visit")
]
continuous_outcomes = [c for c in df.columns if c.startswith("delta_")]

rows = []
for outcome in binary_outcomes:
    for exposure in exposures:
        cols = [outcome, exposure, "baseline_AGE", "sex_numeric"]
        x = df[cols].replace([np.inf, -np.inf], np.nan).dropna()
        if len(x) < 100:
            continue
        events = int(x[outcome].sum())
        nonevents = int(len(x) - events)
        if events < 10 or nonevents < 10:
            continue
        X = sm.add_constant(x[[exposure, "baseline_AGE", "sex_numeric"]], has_constant="add")
        try:
            fit = sm.GLM(x[outcome], X, family=sm.families.Binomial()).fit()
            beta = float(fit.params[exposure])
            se = float(fit.bse[exposure])
            p = float(fit.pvalues[exposure])
            rows.append({
                "model": "logistic",
                "outcome": outcome,
                "exposure": exposure,
                "n": int(len(x)),
                "events": events,
                "beta": beta,
                "se": se,
                "effect": float(np.exp(beta)),
                "ci_low": float(np.exp(beta - 1.96 * se)),
                "ci_high": float(np.exp(beta + 1.96 * se)),
                "p": p,
            })
        except Exception:
            pass

for outcome in continuous_outcomes:
    for exposure in exposures:
        cols = [outcome, exposure, "baseline_AGE", "sex_numeric"]
        x = df[cols].replace([np.inf, -np.inf], np.nan).dropna()
        if len(x) < 100:
            continue
        X = sm.add_constant(x[[exposure, "baseline_AGE", "sex_numeric"]], has_constant="add")
        try:
            fit = sm.OLS(x[outcome], X).fit(cov_type="HC3")
            beta = float(fit.params[exposure])
            se = float(fit.bse[exposure])
            p = float(fit.pvalues[exposure])
            rows.append({
                "model": "linear_HC3",
                "outcome": outcome,
                "exposure": exposure,
                "n": int(len(x)),
                "events": np.nan,
                "beta": beta,
                "se": se,
                "effect": beta,
                "ci_low": beta - 1.96 * se,
                "ci_high": beta + 1.96 * se,
                "p": p,
            })
        except Exception:
            pass

res = pd.DataFrame(rows)
if len(res):
    res["q_fdr"] = np.nan
    for model, idx in res.groupby("model").groups.items():
        q = multipletests(res.loc[idx, "p"].values, method="fdr_bh")[1]
        res.loc[idx, "q_fdr"] = q
    res = res.sort_values(["q_fdr", "p"])
res.to_csv(OUT / "AGING_OUTCOME_ASSOCIATIONS.tsv", sep="\t", index=False)

qc = {
    "merged_subjects": int(len(df)),
    "exposures_tested": exposures,
    "binary_outcomes": binary_outcomes,
    "continuous_outcomes": continuous_outcomes,
    "models_completed": int(len(res)),
}
(OUT / "STAGE6_ASSOCIATION_QC.json").write_text(json.dumps(qc, indent=2))
print(json.dumps(qc, indent=2))
