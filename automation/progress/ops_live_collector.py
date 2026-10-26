"""Collect actual GitHub Actions scheduled runs and live Sheets evidence, read-only."""
import json
import os
from pathlib import Path
from tracker import get, SHEET_ID
from ops_evidence import assess

WORKFLOWS={
 "progress_audit":"automation-progress-audit.yml",
 "evidence_publisher":"automation-progress-evidence-publisher.yml",
 "gate_gap_sync":"automation-gate-gaps-sheet.yml"
}
def github_records(fetch, token=None):
    records={}
    for key,workflow in WORKFLOWS.items():
        url="https://api.github.com/repos/kimtk94/Codex/actions/workflows/"+workflow+"/runs?per_page=100"
        result=fetch(url,token)
        records[key]=[{"id":x["id"],"event":x.get("event"),"conclusion":x.get("conclusion"),
            "status":x.get("status"),"url":x.get("html_url"),"created_at":x.get("created_at")}
            for x in result.get("workflow_runs",[])]
    return records

def read_sheet_snapshot():
    raw=os.getenv("CKD_DRIVE_SA_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return {"state":"NOT_CHECKED","reason":"credentials_missing"}
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    cred=service_account.Credentials.from_service_account_info(json.loads(raw),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(cred)
    url="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET_ID+"/values/'Automation%20Master%20Progress'!A52:J53"
    response=session.get(url,timeout=25)
    response.raise_for_status()
    rows=response.json().get("values",[])
    if len(rows)!=2 or [r[0] for r in rows] != ["A47","A48"]:
        return {"state":"FAILED_ID_GUARD"}
    # A populated PR link or last-checked timestamp is not proof that a scheduled publisher wrote it.
    return {"state":"READ_OK","last_checked_kst":next((r[7] for r in rows if len(r)>7 and r[7]),""),
       "evidence_url":next((r[5] for r in rows if len(r)>5 and r[5]),""),
       "verified_publish_receipt":False,
       "reason":"No verified scheduled publisher receipt matching run_id, timestamp, and changed cell values",
       "row_ids":["A47","A48"]}

def main():
    records=github_records(get,os.getenv("GITHUB_TOKEN"))
    sheet=read_sheet_snapshot()
    verdict=assess(records,sheet)
    verdict["sheet_probe_state"]=sheet["state"]
    verdict["live_github_run_counts"]={k:len(v) for k,v in records.items()}
    folder=Path("progress-audit")
    folder.mkdir(exist_ok=True)
    (folder/"ops01-live-evidence.json").write_text(json.dumps(verdict,ensure_ascii=False,indent=2),encoding="utf-8")
    print("OPS_LIVE_AUDIT",verdict["gate_OPS_01"],verdict["sheet_publish_readback"],sheet["state"])

if __name__=="__main__":
    main()
