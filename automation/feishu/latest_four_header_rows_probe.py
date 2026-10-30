#!/usr/bin/env python3
"""Read-only, redacted Feishu Receipt/eTax top-row structure diagnostic.

At most 6 rows x 52 cells from latest Feishu originals. Never log raw cell
values, hashes of customer data, recipients, amounts or formulas. Compare
only header-position matches with the already-authenticated Google mirror.
This tool does NOT approve raw schema, invoice issuance or bank settlement.
"""
import collections
import datetime as dt
import json
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo
from latest_four_formats import select
from latest_four_mirror_parity import MIRRORS,manifest_map,norm

MAX_ROWS=6
TOP_FORMATS=("Payment Receipt","eTax Invoice")
BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"

def kind(value):
    if value is None or value=="":return "NULL"
    if isinstance(value,str):return "TEXT"
    if isinstance(value,bool):return "BOOLEAN"
    if isinstance(value,(int,float)):return "NUMBER"
    if isinstance(value,dict):return "OBJECT"
    if isinstance(value,list):return "ARRAY"
    return "OTHER"

def analyze_rows(raw_rows,mirror_header,core_width,required_positions=(),max_rows=MAX_ROWS):
    if not isinstance(raw_rows,list):raise ValueError("ROWS_NOT_LIST")
    if not isinstance(mirror_header,list) or len(mirror_header)<core_width:
        raise ValueError("MIRROR_HEADER_WIDTH_INVALID")
    candidate_positions=set()
    summaries=[]
    for number,row in enumerate(raw_rows[:max_rows],start=1):
        if not isinstance(row,list):raise ValueError("ROW_NOT_LIST")
        if len(row)>52:raise ValueError("ROW_TOO_WIDE")
        types=collections.Counter(kind(x) for x in row)
        # Pad sparse/truncated API rows with nulls before positional comparison.
        for _ in range(52-len(row)):types["NULL"]+=1
        matches=[]
        for index in range(min(len(row),core_width)):
            cell=row[index]
            if isinstance(cell,str) and norm(cell) and norm(cell)==norm(mirror_header[index]):
                matches.append(index+1)
                candidate_positions.add(index+1)
        summaries.append({"row":number,"types":dict(sorted(types.items())),
          "matched_core_positions":matches,
          "same_column_mirror_matches":len(matches)})
    required=set(required_positions or range(1,core_width+1))
    covered=sorted(candidate_positions&required)
    missing=sorted(required-candidate_positions)
    # A merged-header false positive can match a handful of general labels.
    # Never pass a raw schema or infer financial state from this diagnostic.
    return {"row_summaries":summaries,
            "required_position_matches_across_sample":covered,
            "missing_required_positions":missing,
            "raw_header_status":"STRUCTURE_UNRESOLVED" if missing else "CANDIDATE_ONLY_REQUIRE_RAW_SCHEMA_AUDIT",
            "certified":False}

def verify_mirror_identity(fmt,selected,manifest):
    live=selected.get(fmt)
    meta=manifest.get(fmt)
    if not live or not meta:raise RuntimeError("LATEST_SOURCE_OR_MIRROR_NOT_FOUND")
    if live["sheet_id"]!=meta["id"] or live["date"]!=meta["date"]:
        raise RuntimeError("SOURCE_ID_OR_DATE_MISMATCH")
    if meta["schema"]!="HEADER_MATCHED":
        raise RuntimeError("MIRROR_SCHEMA_UNVERIFIED")
    return live["sheet_id"]

def main():
    # Authentication only on main / authorized workflow; PR runs synthetic tests.
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    from sheets_tab_discovery import api,TOKEN
    raw=os.getenv("CKD_DRIVE_SA_JSON")
    if not raw:raise RuntimeError("MIRROR_CREDENTIAL_MISSING")
    credentials=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    g=AuthorizedSession(credentials)
    def read_mirror(range_):
        url="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+urllib.parse.quote(range_,safe="")
        response=g.get(url,timeout=35)
        response.raise_for_status()
        return response.json().get("values",[])
    manifest=manifest_map(read_mirror("'Feishu Source Manifest'!A1:G10"))
    auth=api("/open-apis/auth/v3/tenant_access_token/internal",payload={
        "app_id":os.environ["FEISHU_APP_ID"],"app_secret":os.environ["FEISHU_APP_SECRET"]})
    bearer=auth.get("tenant_access_token")
    if not bearer:raise RuntimeError("FEISHU_AUTH_FAILED")
    root="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")
    sheets=api(root+"/sheets/query",bearer).get("sheets")
    if not isinstance(sheets,list):raise RuntimeError("SOURCE_LIST_UNAVAILABLE")
    latest,_=select(sheets,dt.datetime.now(ZoneInfo("Asia/Seoul")).date())
    if latest is None:raise RuntimeError("LATEST_FOUR_INCOMPLETE")
    source_root="/open-apis/sheets/v2/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")
    for fmt in TOP_FORMATS:
        source_id=verify_mirror_identity(fmt,latest,manifest)
        tab,width,fields=MIRRORS[fmt]
        mirror=read_mirror("'"+tab+"'!A1:AZ1")
        if len(mirror)!=1:raise RuntimeError("MIRROR_HEADER_UNAVAILABLE")
        # Latest source UID only. Read actual top 6 rows and print aggregate
        # structural shape; no raw customer values are ever displayed.
        area=urllib.parse.quote(source_id+"!A1:AZ"+str(MAX_ROWS),safe="!:")
        raw_result=api(source_root+"/values/"+area,bearer)
        value_range=raw_result.get("valueRange")
        if not isinstance(value_range,dict):raise RuntimeError("RAW_RANGE_UNAVAILABLE")
        rows=value_range.get("values") or []
        result=analyze_rows(rows,mirror[0],width,fields.keys())
        print("FEISHU_TOP_ROWS "+json.dumps({"format":fmt,
            "max_rows":MAX_ROWS,"mirror_latest_id_date_match":True,
            **result},sort_keys=True))
    print("RAW_HEADER_VERIFIED: NO")
    print("SOURCE_MUTATIONS: 0; PAYMENT_CERTIFIED: NO; ETAX_CERTIFIED: NO")
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        # Do not log raw Feishu responses, auth objects or customer cell data.
        print("FEISHU_TOP_ROWS_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
