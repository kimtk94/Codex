#!/usr/bin/env python3
"""Read-only parity: latest Feishu sheet IDs vs verified Google mirror header layouts.
Structural checks do NOT certify bank payments, invoice issuance, or raw Feishu headers.
Never log cell data or private labels.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
MIRRORS={
 "Payment Outstanding":("Feishu Latest Outstanding",17,{1:"Customer Name",2:"ERP Invoice Number",6:"Project Number",13:"Invoice Amount",14:"Balance"}),
 "Payment Receipt":("Feishu Latest Receipts",13,{1:"Deposit Date",2:"Customer Name",3:"Amount (KRW)",4:"CMS No.",6:"Date",7:"CMS No. [2]",8:"Amount",10:"Date [2]",11:"Customer Name [2]",12:"Amount [2]",13:"CMS No. [3]"}),
 "eTax Invoice":("Feishu Latest eTax",35,{1:"Comments",5:"ERP Invoice Number",10:"Project Number",16:"Amount",26:"Sales",31:"Paid? Yes ?",32:"Status",33:"e-Tax issued?"}),
 "Prepayments":("Feishu Latest Prepayments",19,{1:"N/O",2:"Customer Name",3:"ERP Invoice Number",8:"Invoice Amount",9:"Payment Status",11:"Remaining Prepayment (KRW)",19:"Sales"}),
}

def norm(value):
 return " ".join(str(value or "").casefold().split())

def validate_structure(fmt,header):
 if fmt not in MIRRORS:return "UNKNOWN_FORMAT"
 _tab,width,expected=MIRRORS[fmt]
 if len(header)<width:return "CANONICAL_WIDTH_MISSING"
 core=[norm(v) for v in header[:width]]
 if any(not v for v in core):return "CANONICAL_EMPTY_FIELD"
 if len(set(core))!=len(core):return "CANONICAL_DUPLICATE_FIELD"
 for pos,name in expected.items():
  if core[pos-1]!=norm(name):return "CRITICAL_FIELD_MISMATCH_AT_COL_"+str(pos)
 return "MIRROR_STRUCTURAL_MATCH"

def manifest_map(rows):
 if not rows or rows[0][:4]!=["Source","Source Date","Synced At KST","Source ID"]:
  raise RuntimeError("SOURCE_MANIFEST_SCHEMA_CHANGED")
 found={}
 for r in rows[1:]:
  if not r or r[0] not in MIRRORS:continue
  name=str(r[0])
  if name in found:raise RuntimeError("SOURCE_MANIFEST_DUPLICATE_FORMAT")
  found[name]={"date":str(r[1]) if len(r)>1 else "",
   "id":str(r[3]) if len(r)>3 else "",
   "rows":str(r[4]) if len(r)>4 else "",
   "schema":str(r[5]) if len(r)>5 else ""}
 return found

def evaluate(selected,manifest_rows,headers):
 manifest=manifest_map(manifest_rows)
 reports=[];blocked=[]
 for fmt,(tab,width,expected) in MIRRORS.items():
  meta=manifest.get(fmt,{});live=selected.get(fmt,{})
  problems=[]
  if not live.get("sheet_id") or not live.get("date"):problems.append("FEISHU_LATEST_SOURCE_NOT_IDENTIFIED")
  if not meta.get("id") or not meta.get("date"):problems.append("GOOGLE_MIRROR_MANIFEST_MISSING")
  if live.get("sheet_id") and meta.get("id") and live["sheet_id"]!=meta["id"]:
   problems.append("MIRROR_SOURCE_ID_NOT_LATEST")
  if live.get("date") and meta.get("date") and live["date"]!=meta["date"]:
   problems.append("MIRROR_SOURCE_DATE_NOT_LATEST")
  if meta.get("schema")!="HEADER_MATCHED":problems.append("MIRROR_MANIFEST_SCHEMA_NOT_MATCHED")
  if not meta.get("rows","").isdigit():problems.append("MIRROR_MANIFEST_ROW_COUNT_MISSING")
  structure=validate_structure(fmt,headers.get(fmt,[]))
  if structure!="MIRROR_STRUCTURAL_MATCH":problems.append(structure)
  if problems:blocked.append(fmt)
  reports.append({"format":fmt,"status":"MIRROR_PARITY_BLOCKED" if problems else "MIRROR_MATCH_RAW_UNVERIFIED",
    "checks":problems,"source_date":meta.get("date",""),
    "row_count":int(meta["rows"]) if meta.get("rows","").isdigit() else None,
    "core_columns":width})
 return reports,blocked

def sheet_read(client,tab,area):
 range_id=urllib.parse.quote("'"+tab+"'!"+area,safe="")
 resp=client.get("https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+range_id,timeout=35)
 resp.raise_for_status()
 return resp.json().get("values",[])

def main():
 # Deferred import: synthetic unit tests require no live tokens or packages.
 from google.oauth2 import service_account
 from google.auth.transport.requests import AuthorizedSession
 from latest_four_formats import select
 from sheets_tab_discovery import api,TOKEN
 credentials=os.environ.get("CKD_DRIVE_SA_JSON")
 if not credentials:raise RuntimeError("GOOGLE_MIRROR_CREDENTIALS_MISSING")
 auth=service_account.Credentials.from_service_account_info(json.loads(credentials),
  scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
 session=AuthorizedSession(auth)
 manifest=sheet_read(session,"Feishu Source Manifest","A1:G10")
 headers={fmt:sheet_read(session,tab,"A1:AZ1")[0]
  for fmt,(tab,_,__) in MIRRORS.items()}
 feishu_auth=api("/open-apis/auth/v3/tenant_access_token/internal",payload={
   "app_id":os.environ["FEISHU_APP_ID"],"app_secret":os.environ["FEISHU_APP_SECRET"]})
 endpoint="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")+"/sheets/query"
 originals=api(endpoint,feishu_auth["tenant_access_token"]).get("sheets")
 if not isinstance(originals,list):raise RuntimeError("FEISHU_SOURCE_LIST_UNAVAILABLE")
 selected,_=select(originals,dt.datetime.now(ZoneInfo("Asia/Seoul")).date())
 if selected is None:raise RuntimeError("FEISHU_LATEST_FOUR_NOT_FOUND")
 reports,blocked=evaluate(selected,manifest,headers)
 for item in reports:print("FEISHU_MIRROR_PARITY "+json.dumps(item,sort_keys=True))
 print("MIRROR_ROLE: STRUCTURAL_CROSS_CHECK; RAW_HEADER_GATE_NOT_OVERRIDDEN")
 print("SETTLEMENT_CERTIFIED: NO; ISSUANCE_CERTIFIED: NO; SOURCE_WRITES: 0")
 if blocked:raise RuntimeError("MIRROR_PARITY_BLOCKED_FORMATS="+",".join(blocked))
 print("MIRROR_PARITY_PASS_RAW_STILL_UNVERIFIED")
 return 0

if __name__=="__main__":
 try:sys.exit(main())
 except Exception as exc:
  reason=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
  print("FEISHU_MIRROR_PARITY_FAILED: "+reason[:200],file=sys.stderr)
  sys.exit(1)
