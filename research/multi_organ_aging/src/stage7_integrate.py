from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from common import ensure_dir, json_dump, load_config, write_table

def read_if(path):
    p=Path(path)
    if not p.exists():
        return None
    try:
        if p.suffix==".json":
            return json.loads(p.read_text(encoding="utf-8"))
        return pd.read_csv(p,sep="\t",compression="infer",low_memory=False)
    except Exception:
        return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--out-dir")
    a=ap.parse_args()
    cfg=load_config(a.config)
    root=Path(a.out_dir or cfg["paths"]["out_dir"])
    out=ensure_dir(root/"stage7_integrated")

    perf=read_if(root/"stage2_clocks"/"ORGAN_CLOCK_PERFORMANCE.tsv")
    pace=read_if(root/"stage3_pace"/"SUBJECT_ORGAN_AGING_PACE.tsv.gz")
    cl=read_if(root/"stage4_discordance"/"CLUSTER_COUNTS.tsv")
    outcome=read_if(root/"stage5_outcomes"/"OUTCOME_ASSOCIATIONS.tsv")
    genetics=read_if(root/"stage6_genetics"/"PRS_AGING_PACE_ASSOCIATIONS.tsv")

    rows=[]
    if isinstance(perf,pd.DataFrame):
        for _,r in perf.iterrows():
            if str(r.get("status",""))!="ok":
                continue
            organ=str(r["organ"])
            pr=pace[pace["organ"].eq(organ)] if isinstance(pace,pd.DataFrame) else pd.DataFrame()
            rows.append({
                "organ":organ,
                "clock_n":r.get("n_rows"),
                "clock_oof_mae":r.get("oof_mae"),
                "clock_oof_r2":r.get("oof_r2"),
                "gap_age_corr_after":r.get("corr_gap_age_after"),
                "pace_n":int(pr.person_id.nunique()) if not pr.empty else 0,
                "median_pace_z_per_year":pr.huber_slope_z_per_year.median() if not pr.empty else None,
                "pace_iqr":(pr.huber_slope_z_per_year.quantile(.75)-pr.huber_slope_z_per_year.quantile(.25)) if not pr.empty else None
            })
    matrix=pd.DataFrame(rows)
    write_table(matrix,out/"ORGAN_EVIDENCE_MATRIX.tsv")

    sig_out=0
    if isinstance(outcome,pd.DataFrame) and "q_fdr" in outcome.columns:
        sig_out=int((pd.to_numeric(outcome.q_fdr,errors="coerce")<0.05).sum())
    sig_gen=0
    if isinstance(genetics,pd.DataFrame) and "q_fdr" in genetics.columns:
        sig_gen=int((pd.to_numeric(genetics.q_fdr,errors="coerce")<0.05).sum())

    summary={
        "trained_organs":matrix.organ.tolist() if not matrix.empty else [],
        "n_trained_organs":int(len(matrix)),
        "subject_organ_pace_rows":int(len(pace)) if isinstance(pace,pd.DataFrame) else 0,
        "clusters":cl.to_dict(orient="records") if isinstance(cl,pd.DataFrame) else [],
        "fdr_significant_outcome_models":sig_out,
        "fdr_significant_genetic_models":sig_gen,
        "interpretation_guardrails":[
            "Organ age is a model-derived phenotype, not literal tissue age.",
            "Longitudinal pace is relative to the cohort clock and age-gap residualization.",
            "Cluster labels are descriptive and require bootstrap/replication stability checks.",
            "PRS associations do not establish causality.",
            "Primary hypotheses must be frozen before controlled outcomes are inspected."
        ]
    }
    json_dump(summary,out/"INTEGRATED_SUMMARY.json")

    md=[
        "# Multi-organ Aging Integrated Run Summary","",
        f"- Trained organs: {', '.join(summary['trained_organs']) or 'none'}",
        f"- Subject-organ pace rows: {summary['subject_organ_pace_rows']}",
        f"- FDR-significant outcome models: {sig_out}",
        f"- FDR-significant genetic models: {sig_gen}","",
        "## Interpretation guardrails"
    ]
    md += [f"- {x}" for x in summary["interpretation_guardrails"]]
    (out/"INTEGRATED_RUN_REPORT.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print(summary)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
