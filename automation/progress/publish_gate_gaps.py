"""Publish gate gap counts/reasons to G:I only; never change verdict D or evidence E."""
import argparse
import json
import os
from pathlib import Path
from gate_gap_report import gap_rows
from tracker import SHEET_ID

TAB = "Automation Gate Summary"
EXPECTED = ["SRC-01","SRC-02","ID-01","FIN-01","FIN-02","FIN-03","NBA-01","TAT-01","RPA-01","RPA-02","WEB-01","OPS-01","OPS-02"]

def prepare(gates, sheet_ids):
    if sheet_ids != EXPECTED or [g["gate_id"] for g in gates] != EXPECTED:
        raise ValueError("Gate IDs/order mismatch; stop before writes")
    return [[g["missing_task_count"], ", ".join(g["missing_reasons"]),
             "Unsigned acceptance registry; informational only"] for g in gates]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--apply",action="store_true")
    a=p.parse_args()
    if a.apply and os.getenv("GATE_GAP_APPLY") != "true":
        raise RuntimeError("Explicit GATE_GAP_APPLY=true required")
    raw=os.environ.get("CKD_DRIVE_SA_JSON") or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Google credentials missing")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    cred=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session=AuthorizedSession(cred)
    endpoint="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET_ID
    url=endpoint+"/values/'Automation%20Gate%20Summary'!A5:A17"
    response=session.get(url,timeout=20)
    response.raise_for_status()
    ids=[r[0] if r else "" for r in response.json().get("values",[])]
    manifest=json.loads(Path("automation/progress/acceptance_manifest.json").read_text())
    from acceptance_registry import REGISTRY, verify
    from tracker import tasks, MASTER
    registry=json.loads(REGISTRY.read_text(encoding="utf-8"))
    task_ids={t["id"] for t in tasks(Path(MASTER).read_text(encoding="utf-8"))}
    verify(registry,manifest,task_ids)
    rows=prepare(gap_rows(manifest,registry["records"]),ids)
    output=Path("progress-audit/gate-sheet-preview.json")
    output.parent.mkdir(exist_ok=True)
    state={"gate_count":len(rows),"range":"'Automation Gate Summary'!G5:I17",
           "mode":"PREVIEW" if not a.apply else "APPLY","preserves":["A:F","J:","all other tabs"]}
    output.write_text(json.dumps(state,indent=2))
    if not a.apply:
        print(json.dumps(state))
        return
    fresh=session.get(url,timeout=20)
    fresh.raise_for_status()
    if [r[0] if r else "" for r in fresh.json().get("values",[])] != ids:
        raise ValueError("Concurrent gate reorder")
    result=session.put(endpoint+"/values/'Automation%20Gate%20Summary'!G5:I17",
                       params={"valueInputOption":"RAW"},json={"majorDimension":"ROWS","values":rows},timeout=30)
    result.raise_for_status()
    print("GATE_GAP_SHEET_OK",len(rows))

if __name__=="__main__":
    main()
