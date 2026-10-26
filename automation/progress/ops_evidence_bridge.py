"""Consolidate live scheduled-run evidence with independent receipt verification."""
import json
from pathlib import Path

def combine(live, receipt):
    out=dict(live)
    receipt_ok=(receipt.get("state")=="OBSERVED"
        and receipt.get("reason")=="MATCHING_SCHEDULED_WRITE_AND_CURRENT_CELLS"
        and isinstance(receipt.get("run_id"),int))
    out["independent_receipt"]={
        "state":receipt.get("state","NOT_CHECKED"),
        "run_id":receipt.get("run_id"),
        "reason":receipt.get("reason","not_available")}
    out["sheet_publish_readback"]="OBSERVED" if receipt_ok else "NOT_OBSERVED"
    missing=[x for x in out.get("missing_requirements",[]) if x!="sheet_publish_readback"]
    if not receipt_ok:
        missing.append("sheet_publish_readback")
    out["missing_requirements"]=missing
    # Never mark OPS-01 accepted on a receipt alone: alerts, recovery and human review remain required.
    out["gate_OPS_01"]="NOT_VERIFIED"
    out["task_A48"]="NOT_VERIFIED"
    return out

def main():
    folder=Path("progress-audit")
    source=folder/"ops01-live-evidence.json"
    receipt_file=folder/"independent-write-receipt.json"
    live=json.loads(source.read_text()) if source.exists() else {}
    receipt=json.loads(receipt_file.read_text()) if receipt_file.exists() else {"state":"NOT_CHECKED","reason":"receipt_report_missing"}
    result=combine(live,receipt)
    dest=folder/"ops01-consolidated.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(result,indent=2))
    print("OPS01_CONSOLIDATED",result["sheet_publish_readback"],result["gate_OPS_01"])

if __name__=="__main__":
    main()
