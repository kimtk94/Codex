#!/usr/bin/env python3
"""Compare original undated Feishu eTax Base vs dated Feishu Sheets snapshot.

Only source evidence and generated Google audit rows are written. A match is
NOT issued-this-month evidence, paid evidence, or owner/Revenue approval.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

from base_readonly_probe import request, require
from payment_table_audit import list_pages
from sheets_tab_discovery import api as sheets_api, TOKEN
from latest_four_formats import select

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB = "Feishu eTax Base Sheet Crosswalk"
HEAD = ["Key Type","Invoice Identifier","Base Amount KRW","Dated Sheet Amount KRW",
        "Evidence","Snapshot Date","Source Age Days","Payment / Issuance",
        "Review Boundary","Checked KST","GitHub Run"]
ALIAS = {
    "CMS": ("CMS Invoice Number", "CMS Invoice Num", "CMS Invoice No", "CMS No."),
    "ERP": ("ERP Invoice Number", "ERP Invoice No"),
    "AMOUNT": ("Amount", "Invoice Amount", "Invoice Amount KRW", " Invoice Amount "),
}

def norm(text):
    return " ".join(re.sub(r"[-_]"," ",str(text or "")).casefold().split())

def scalar(value):
    if isinstance(value,(str,int,float)):
        return str(value).strip()
    if isinstance(value,list) and len(value)==1:
        return scalar(value[0])
    if isinstance(value,dict) and set(value)&{"text","value"}:
        return scalar(value.get("text",value.get("value")))
    return ""

def money(value):
    value=scalar(value).replace(",","").replace("₩","").replace("KRW","").strip()
    if not re.fullmatch(r"\d+(?:\.0{1,2})?",value):
        return None
    return int(value.split(".")[0])

def invoice_id(value):
    text=scalar(value)
    return text if re.fullmatch(r"20\d{7,12}(?:-\d{1,3})?",text) else ""

def column_map(headers):
    result={}
    for key,names in ALIAS.items():
        matched=[idx for idx,h in enumerate(headers) if norm(h) in {norm(n) for n in names}]
        if len(matched)>1:raise ValueError("AMBIGUOUS_COLUMN_"+key)
        result[key]=matched[0] if matched else None
    return result

def flatten(source,columns,dict_mode=False):
    records=[]
    for row in source:
        fields=row.get("fields") or {} if dict_mode else None
        out={}
        for key,idx in columns.items():
            if idx is None:
                out[key]=""
            elif dict_mode:
                out[key]=scalar(fields.get(idx))  # idx is a field NAME in dict mode
            else:
                out[key]=scalar(row[idx]) if idx<len(row) else ""
        out["AMOUNT"]=money(out["AMOUNT"])
        for kind in ("CMS","ERP"):out[kind]=invoice_id(out[kind])
        records.append(out)
    return records

def crosswalk(base,sheet,snapshot,now):
    if now.tzinfo is None:raise ValueError("CLOCK_NEEDS_TIMEZONE")
    if snapshot>now.date() or snapshot.year!=now.year or snapshot.month!=now.month:
        raise ValueError("SNAPSHOT_MONTH_UNVERIFIED")
    if not base or not sheet:raise ValueError("SOURCE_EMPTY")
    age=(now.date()-snapshot).days
    counts=collections.Counter()
    index={kind:collections.defaultdict(list) for kind in ("CMS","ERP")}
    for j,item in enumerate(sheet):
        for kind in index:
            if item.get(kind):index[kind][item[kind]].append(j)
    used=set()
    results=[]
    for b in base:
        candidates=set()
        for kind in index:
            key=b.get(kind)
            if key:candidates.update(index[kind].get(key,[]))
        qualified=[(k,b[k]) for k in ("CMS","ERP") if b.get(k)]
        keytype,keyval=qualified[0] if qualified else ("UNVERIFIED","")
        exact_sheet_amount=""
        if not qualified:state="NO_VERIFIABLE_INVOICE_KEY"
        elif not candidates:state="BASE_ONLY_NOT_IN_DATED_SNAPSHOT"
        elif len(candidates)>1:state="AMBIGUOUS_SNAPSHOT_MATCH"
        else:
            idx=next(iter(candidates))
            s=sheet[idx]
            # A matched row must not conflict on a second populated shared ID.
            disagreement=any(b.get(k) and s.get(k) and b[k]!=s[k] for k in ("CMS","ERP"))
            sibling=sum(1 for other in base if any(
                other is not b and other.get(k) and other[k]==b.get(k)
                for k in ("CMS","ERP") if b.get(k)))
            exact_sheet_amount=s.get("AMOUNT") if s.get("AMOUNT") is not None else ""
            if sibling or disagreement:
                state="DUPLICATE_OR_CONFLICTING_ID_REVIEW"
            elif b.get("AMOUNT") is None or s.get("AMOUNT") is None:
                state="AMOUNT_NOT_COMPARABLE"
            elif b["AMOUNT"]!=s["AMOUNT"]:
                state="ID_MATCH_AMOUNT_CONFLICT"
            else:
                state="ID_AND_AMOUNT_MATCHED_SNAPSHOT_ONLY"
                used.add(idx)
        counts[state]+=1
        results.append([keytype,keyval,b.get("AMOUNT") if b.get("AMOUNT") is not None else "",
            exact_sheet_amount,state,snapshot.isoformat(),age,"NOT_VERIFIED",
            "A 10/26 dated snapshot is not a current eTax issuance or bank receipt",
            now.strftime("%Y-%m-%d %H:%M:%S KST"),""])
    for i,s in enumerate(sheet):
        if i in used:continue
        # Show dated only entries distinctly without asserting that Base is missing
        # when it merely has ambiguous IDs.
        keytype,keyval=next(((k,s[k]) for k in ("CMS","ERP") if s.get(k)),("UNVERIFIED",""))
        state="DATED_ONLY_OR_UNRESOLVED_REVIEW"
        counts[state]+=1
        results.append([keytype,keyval,"",s.get("AMOUNT") if s.get("AMOUNT") is not None else "",
            state,snapshot.isoformat(),age,"NOT_VERIFIED",
            "No current-month issuance, owner or payment certification",
            now.strftime("%Y-%m-%d %H:%M:%S KST"),""])
    return results,{"base_records":len(base),"dated_rows":len(sheet),"source_age_days":age,
                    "exact_matches":counts["ID_AND_AMOUNT_MATCHED_SNAPSHOT_ONLY"],
                    "states":dict(sorted(counts.items())),"payment_certified":0,
                    "issuance_certified":0,"source_write_count":0}

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    now=dt.datetime.now(ZoneInfo("Asia/Seoul"))
    if not os.getenv("CKD_DRIVE_SA_JSON") or not os.getenv("GITHUB_RUN_ID","").isdigit():
        raise RuntimeError("GITHUB_EVIDENCE_AUTH_MISSING")
    if os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":raise RuntimeError("REPO_SCOPE_INVALID")
    auth=request("POST","/open-apis/auth/v3/tenant_access_token/internal",
        body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    if auth.get("code")!=0 or not auth.get("tenant_access_token"):
        raise RuntimeError("FEISHU_AUTH_FAILED")
    token=auth["tenant_access_token"]
    prefix="/open-apis/bitable/v1/apps/"+urllib.parse.quote(require("FEISHU_BASE_APP_TOKEN"),safe="")
    tables=list(list_pages(prefix+"/tables",token))
    matches=[t for t in tables if norm(t.get("name"))=="etax invoice"]
    if len(matches)!=1:raise RuntimeError("BASE_ETAX_GENERIC_NOT_UNIQUE")
    root=prefix+"/tables/"+urllib.parse.quote(matches[0]["table_id"],safe="")
    fields=list(list_pages(root+"/fields",token))
    records=list(list_pages(root+"/records",token))
    ids=[r.get("record_id") for r in records]
    if not ids or any(not x for x in ids) or len(set(ids))!=len(ids):
        raise RuntimeError("BASE_RECORD_KEY_PROVENANCE_INVALID")
    by_name=column_map([f["field_name"] for f in fields])
    field_names=[f["field_name"] for f in fields]
    named={key:field_names[i] if i is not None else None for key,i in by_name.items()}
    if all(named.get(k) is None for k in ("CMS","ERP")):
        raise RuntimeError("BASE_NO_RECONCILABLE_ID_SCHEMA")
    if named.get("AMOUNT") is None:raise RuntimeError("BASE_AMOUNT_SCHEMA_UNVERIFIED")
    base=flatten(records,named,dict_mode=True)

    path="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")
    source_sheets=sheets_api(path+"/sheets/query",token).get("sheets")
    if not isinstance(source_sheets,list):raise RuntimeError("SHEETS_LIST_MISSING")
    selected,_=select(source_sheets,now.date())
    if selected is None:raise RuntimeError("DATED_SHEET_SELECTION_UNVERIFIED")
    info=selected["eTax Invoice"]
    date=dt.date.fromisoformat(info["date"])
    if (date.year,date.month)!=(now.year,now.month):
        raise RuntimeError("DATED_SHEET_NOT_CURRENT_MONTH")
    # Original Feishu worksheet: row 1 is a merged title; row 2 headers.
    valuepath=("/open-apis/sheets/v2/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")+
        "/values/"+urllib.parse.quote(info["sheet_id"]+"!A2:AI4000",safe="!:"))
    raw=sheets_api(valuepath,token).get("valueRange") or {}
    rows=raw.get("values") or []
    if len(rows)<2:raise RuntimeError("DATED_SHEET_ROWS_MISSING")
    columns=column_map(rows[0])
    if columns.get("AMOUNT") is None or all(columns.get(k) is None for k in ("CMS","ERP")):
        raise RuntimeError("DATED_SHEET_KEY_AMOUNT_SCHEMA_MISSING")
    dated=flatten(rows[1:],columns)
    dated=[r for r in dated if any(r.get(k) for k in ("CMS","ERP"))]
    output,stats=crosswalk(base,dated,date,now)
    if len(output)>5000:raise RuntimeError("CROSSWALK_TOO_LARGE")
    service=service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client=AuthorizedSession(service)
    def google(method,url,**kwargs):
        response=client.request(method,url,timeout=55,**kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    prefix="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    metadata=google("GET",prefix,params={"fields":"sheets.properties(title,sheetId)"})
    if not any(s.get("properties",{}).get("title")==TAB for s in metadata.get("sheets",[])):
        google("POST",prefix+":batchUpdate",json={"requests":[{"addSheet":{
            "properties":{"title":TAB,"gridProperties":{"rowCount":5000,
                "columnCount":len(HEAD),"frozenRowCount":1}}}}]})
    link="https://github.com/kimtk94/Codex/actions/runs/"+os.environ["GITHUB_RUN_ID"]
    cells=[HEAD]+[r[:-1]+[link] for r in output]
    location=prefix+"/values/"+urllib.parse.quote("'"+TAB+"'!A1:K"+str(len(cells)),safe="")
    existing=google("GET",location).get("values",[])
    if existing and existing[0]!=HEAD:raise RuntimeError("FOREIGN_SHEET_HEADER")
    google("PUT",location,params={"valueInputOption":"RAW"},json={"values":cells})
    back=google("GET",location).get("values",[])
    if back!=[[str(v) for v in r] for r in cells]:
        raise RuntimeError("GOOGLE_SHEET_READBACK_FAILED")
    print("FEISHU_ETAX_CROSSWALK="+json.dumps(stats,sort_keys=True))
    print("ORIGINAL_BASE_AND_DATED_SHEET_READ_ONLY;NO_PAYMENT_OR_ISSUANCE_CERTIFICATION")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("FEISHU_ETAX_CROSSWALK_FAILED="+type(e).__name__,file=sys.stderr)
        sys.exit(1)
