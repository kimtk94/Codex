#!/usr/bin/env python3
"""Detect Feishu Sheets tabs without reading cell values or modifying either document."""
import json, os, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path
TOKEN = "MoZasLAK8hUlsAtIhumjVHjYpQe"
BASELINE = Path(__file__).with_name("sheet_ids_baseline.json")

def api(path, bearer=None, payload=None):
    headers={"Content-Type":"application/json"}
    if bearer: headers["Authorization"]="Bearer "+bearer
    req=urllib.request.Request("https://open.feishu.cn"+path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req,timeout=30) as resp: result=json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HTTP_STATUS_"+str(exc.code)) from None
    if result.get("code")!=0: raise RuntimeError("FEISHU_CODE_"+str(result.get("code")))
    return result.get("data") or {}

def main():
    app_id=os.environ["FEISHU_APP_ID"]
    secret=os.environ["FEISHU_APP_SECRET"]
    data=api("/open-apis/auth/v3/tenant_access_token/internal",
             payload={"app_id":app_id,"app_secret":secret})
    bearer=data["tenant_access_token"]
    path="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")+"/sheets/query"
    sheets=api(path,bearer).get("sheets")
    if not isinstance(sheets,list): raise RuntimeError("Missing sheets list")
    ids=[s.get("sheet_id") for s in sheets]
    if any(not x for x in ids) or len(ids)!=len(set(ids)):
        raise RuntimeError("Invalid or duplicated sheet IDs")
    print("SHEETS_AUTH: PASS")
    print("SHEETS_LIST: PASS")
    print("SHEET_COUNT:",len(ids))
    if BASELINE.exists():
        prior=json.loads(BASELINE.read_text(encoding="utf-8"))
        if prior.get("spreadsheet_token")!=TOKEN: raise RuntimeError("Baseline source mismatch")
        known=set(prior["sheet_ids"])
        print("NEW_SHEET_COUNT:",len(set(ids)-known))
        print("MISSING_SHEET_COUNT:",len(known-set(ids)))
        print("NEW_SHEET_IDS:",json.dumps(sorted(set(ids)-known)))
        print("BASELINE_STATUS: ACTIVE")
    else:
        print("BASELINE_STATUS: NEEDS_INITIAL_APPROVAL")
        print("INITIAL_SHEET_IDS:",json.dumps(sorted(ids)))
    print("BASE_TABLE_CREATION: DISABLED")
    print("RECORD_WRITES: 0")
    print("DISCOVERY_DRY_RUN: PASS")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("DISCOVERY_FAILED:",reason,file=sys.stderr)
        sys.exit(1)
