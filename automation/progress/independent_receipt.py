"""Independent, read-only verification of scheduled publisher write receipts."""
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
import requests
from tracker import SHEET_ID

RUNS_API="https://api.github.com/repos/kimtk94/Codex/actions/workflows/automation-progress-evidence-publisher.yml/runs"
ARTIFACT_API="https://api.github.com/repos/kimtk94/Codex/actions/runs/{}/artifacts"
ALLOWED={"F","H","J"}

def verify_receipt(run, receipt, current):
    if run.get("event")!="schedule" or run.get("conclusion")!="success":
        return "NOT_VERIFIED", "NOT_SUCCESSFUL_SCHEDULE"
    if str(receipt.get("run_id"))!=str(run.get("id")) or receipt.get("commit_sha")!=run.get("head_sha"):
        return "NOT_VERIFIED", "RUN_ID_OR_SHA_MISMATCH"
    if receipt.get("state")!="VERIFIED_WRITE_RECEIPT" or receipt.get("spreadsheet_id")!=SHEET_ID:
        return "NOT_VERIFIED", "INVALID_RECEIPT"
    if receipt.get("target_tab")!="Automation Master Progress":
        return "NOT_VERIFIED", "WRONG_TAB"
    cells=receipt.get("verified_cells",[])
    hashes=receipt.get("cell_sha256",{})
    if not cells or len(cells)!=len(set(cells)) or set(cells)!=set(hashes):
        return "NOT_VERIFIED", "MISSING_CELL_HASHES"
    if any(cell[:1] not in ALLOWED or not cell[1:].isdigit() or not 6<=int(cell[1:])<=55 for cell in cells):
        return "NOT_VERIFIED","UNEXPECTED_CELLS"
    if set(current)!=set(cells):
        return "NOT_VERIFIED", "READBACK_INCOMPLETE"
    for cell in cells:
        digest=hashlib.sha256(str(current[cell]).encode("utf-8")).hexdigest()
        if digest!=hashes[cell]:
            return "NOT_VERIFIED","CURRENT_SHEET_CHANGED"
    return "OBSERVED","MATCHING_SCHEDULED_WRITE_AND_CURRENT_CELLS"

def collect():
    token=os.getenv("GITHUB_TOKEN")
    raw=os.getenv("CKD_DRIVE_SA_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not token or not raw:
        return {"state":"NOT_CHECKED","reason":"credentials_missing"}
    headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"}
    response=requests.get(RUNS_API,headers=headers,params={"event":"schedule","per_page":15},timeout=20)
    response.raise_for_status()
    runs=[r for r in response.json().get("workflow_runs",[]) if r.get("conclusion")=="success"]
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    cred=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(cred)
    base="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET_ID
    for run in runs:
        response=requests.get(ARTIFACT_API.format(run["id"]),headers=headers,timeout=20)
        response.raise_for_status()
        artifacts=[a for a in response.json().get("artifacts",[]) if a.get("name")=="automation-evidence-publisher-preview" and not a.get("expired")]
        if not artifacts: continue
        archive=requests.get(artifacts[0]["archive_download_url"],headers=headers,timeout=25)
        archive.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
            matching=[n for n in z.namelist() if n.endswith("publisher-write-receipt.json")]
            if len(matching)!=1: continue
            receipt=json.loads(z.read(matching[0]))
        cells=receipt.get("verified_cells",[])
        if not cells: continue
        data=session.get(base+"/values:batchGet",
            params={"ranges":["'Automation Master Progress'!"+cell for cell in cells],
                    "valueRenderOption":"UNFORMATTED_VALUE"},timeout=25)
        data.raise_for_status()
        ranges=data.json().get("valueRanges",[])
        current={}
        if len(ranges)==len(cells):
            for cell,item in zip(cells,ranges):
                values=item.get("values",[])
                current[cell]=str(values[0][0]) if values and values[0] else ""
        state,reason=verify_receipt(run,receipt,current)
        return {"state":state,"reason":reason,"run_id":run["id"],
                "run_url":run.get("html_url"),"verified_cell_count":len(cells)}
    return {"state":"NOT_OBSERVED","reason":"no_successful_scheduled_run_with_receipt"}

def main():
    result=collect()
    dest=Path("progress-audit/independent-write-receipt.json")
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(result,indent=2))
    print("INDEPENDENT_RECEIPT",result["state"],result["reason"])
if __name__=="__main__":
    main()
