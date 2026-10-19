"""Fail-closed CKD/IS stage readiness: real inputs required, never infer completion."""
import hashlib
import json
import os
from pathlib import Path

STAGES = [
    {"id":"ckd_stage1_pqtl","requires":["pqtl_manifest"],"depends":[]},
    {"id":"ckd_stage2_mr","requires":["mr_inputs"],"depends":["ckd_stage1_pqtl"]},
    {"id":"ckd_stage2b_coloc","requires":["coloc_inputs"],"depends":["ckd_stage2_mr"]},
    {"id":"ckd_stage3_kidney","requires":["kidney_annotation"],"depends":["ckd_stage2b_coloc"]},
    {"id":"ckd_stage4_koges","requires":["koges_controlled_access"],"depends":["ckd_stage3_kidney"]},
]
def assess(available: dict, verified: set[str]) -> dict:
    output=[]
    for stage in STAGES:
        missing=[key for key in stage["requires"] if available.get(key) is not True]
        unmet=[key for key in stage["depends"] if key not in verified]
        # A stage is executable only if verified input material is supplied separately.
        state="READY_FOR_VERIFIED_EXECUTOR" if not missing and not unmet else "BLOCKED_EXTERNAL"
        output.append({"stage":stage["id"],"state":state,"missing_inputs":missing,"unverified_dependencies":unmet,
                       "analysis_executed":False})
    return {"kind":"research_stage_readiness","claims_real_analysis":False,"stages":output}

def main():
    # Do not trust environment flags as evidence of data availability.
    report=assess({},set())
    out=Path("artifacts")
    out.mkdir(exist_ok=True)
    (out/"research-stage-readiness.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    main()
