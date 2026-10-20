"""Deterministic, fail-closed automatic CKD next-action decision.
Only already-implemented and verified report publishing can advance automatically.
Statistical reanalysis and production Vercel deployments remain blocked.
"""
import json
from pathlib import Path

def decide(intake_result, summary=None, published=False):
    if intake_result!="success":
        return {"state":"BLOCKED","next_stage":"drive_intake","reason":"INTAKE_FAILED","auto_execute":False}
    if not isinstance(summary,dict) or summary.get("status")!="CROSS_STAGE_QC_PASS" or summary.get("genes")!=9 or summary.get("scientific_recomputation") is not False:
        return {"state":"BLOCKED","next_stage":"cross_stage_qc","reason":"REPORT_NOT_VERIFIED","auto_execute":False}
    if not published:
        return {"state":"READY","next_stage":"sanitized_report_publish","reason":"QC_PASS","auto_execute":True}
    return {"state":"BLOCKED_EXTERNAL","next_stage":"real_mr_coloc_susie_or_web_integration","reason":"VERIFIED_NUMERIC_INPUTS_AND_WEB_SOURCE_NOT_CONNECTED","auto_execute":False}

def main():
    data=Path("_ckd_published/reports/ckd-summary.json")
    result=decide("success",json.loads(data.read_text()) if data.is_file() else None, published=True)
    out=Path("ckd-next-action.json")
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
if __name__=="__main__": main()
