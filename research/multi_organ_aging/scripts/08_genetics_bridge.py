#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

GENETICS = Path("/srv/is-analysis/data/multi_organ_aging/genetics")
PATTERNS = Path("/srv/is-analysis/results/multi_organ_aging/stage4_patterns/MULTI_ORGAN_AGING_PATTERNS.tsv.gz")
OUTCOMES = Path("/srv/is-analysis/results/multi_organ_aging/stage5_outcomes/LONGITUDINAL_OUTCOMES.tsv.gz")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage7_genetics")


def read_any(path: Path) -> pd.DataFrame:
    for kwargs in ({"sep": "\t"}, {"sep": ","}, {"sep": None, "engine": "python"}):
        try:
            x = pd.read_csv(path, low_memory=False, **kwargs)
            if x.shape[1] > 1:
                return x
        except Exception:
            pass
    raise RuntimeError(f"Cannot parse {path}")


def detect_id(df: pd.DataFrame):
    for c in ["subject_id", "ID", "id", "IID", "iid"]:
        if c in df.columns:
            return c
    return None


OUT.mkdir(parents=True, exist_ok=True)
files = sorted([p for p in GENETICS.glob("*") if p.is_file() and p.suffix.lower() in {".tsv", ".csv", ".txt", ".gz"}])
status = {"status": "no_genetic_input", "files": [str(x) for x in files], "models_completed": 0}

if not files:
    (OUT / "STAGE7_GENETICS_STATUS.json").write_text(json.dumps(status, indent=2))
    print(json.dumps(status, indent=2))
    raise SystemExit(0)

pat = pd.read_csv(PATTERNS, sep="\t")
cov = pd.read_csv(OUTCOMES, sep="\t")[["subject_id", "baseline_AGE", "baseline_SEX"]].copy()
base = pat.merge(cov, on="subject_id", how="left")

all_results = []
for path in files:
    try:
        g = read_any(path)
    except Exception:
        continue
    id_col = detect_id(g)
    if id_col is None:
        continue
    g = g.rename(columns={id_col: "subject_id"})
    g["subject_id"] = g["subject_id"].astype(str)
    score_cols = []
    for c in g.columns:
        if c == "subject_id":
            continue
        s = pd.to_numeric(g[c], errors="coerce")
        if s.notna().sum() >= 100 and s.nunique(dropna=True) > 10:
            g[c] = s
            score_cols.append(c)

    m = base.merge(g[["subject_id"] + score_cols], on="subject_id", how="inner")
    phenos = [c for c in m.columns if c.endswith("_pace_z") or c in {"mean_aging_z", "organ_discordance_z", "aging_pc1"}]
    for score in score_cols:
        for pheno in phenos:
            x = m[[score, pheno, "baseline_AGE"]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(x) < 100:
                continue
            X = sm.add_constant(x[[score, "baseline_AGE"]], has_constant="add")
            try:
                fit = sm.OLS(x[pheno], X).fit(cov_type="HC3")
                beta = float(fit.params[score])
                se = float(fit.bse[score])
                p = float(fit.pvalues[score])
                all_results.append({
                    "source_file": path.name,
                    "score": score,
                    "phenotype": pheno,
                    "n": int(len(x)),
                    "beta": beta,
                    "se": se,
                    "ci_low": beta - 1.96 * se,
                    "ci_high": beta + 1.96 * se,
                    "p": p,
                })
            except Exception:
                pass

res = pd.DataFrame(all_results)
if len(res):
    res["q_fdr"] = multipletests(res["p"].values, method="fdr_bh")[1]
    res = res.sort_values(["q_fdr", "p"])
res.to_csv(OUT / "PRS_ORGAN_AGING_ASSOCIATIONS.tsv", sep="\t", index=False)

status = {
    "status": "completed",
    "files": [str(x) for x in files],
    "models_completed": int(len(res)),
}
(OUT / "STAGE7_GENETICS_STATUS.json").write_text(json.dumps(status, indent=2))
print(json.dumps(status, indent=2))
