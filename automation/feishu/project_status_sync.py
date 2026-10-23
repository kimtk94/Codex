#!/usr/bin/env python3
"""Feishu project-level status -> private unified Sheet. Read-only Feishu, no mail send.

Both eTAX (not issued) and Outstanding (unpaid) are independently retained.
Missing project IDs are excluded and counted; a failed audit cannot erase history.
"""
import datetime as dt
import json, os, re, sys, urllib.parse
from collections import defaultdict
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from base_readonly_probe import request,require
from payment_table_audit import list_pages, TARGET as OUTSTANDING_TABLE
from etax_monthly_audit import select_etax

SHEET=os.getenv("SFDC_UNIFIED_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
KST=dt.timezone(dt.timedelta(hours=9))
HEAD=["Project ID","Tax invoice unissued","Payment outstanding","Priority","Last verified KST","eTAX records","Outstanding records","Source","Amount verified","Next action"]
def normalize(x):return re.sub("[^A-Z0-9]","",str(x or "").upper())
def pick(fields):
    aliases={"project number","project id","amea project id","amea project number","project no"}
    a=[f.get("field_name") for f in fields if " ".join(str(f.get("field_name") or "").strip().lower().replace("_"," ").split()) in aliases]
    return a[0] if len(a)==1 else None
def group(records,field):
    out=defaultdict(int);missing=0
    for row in records:
        val=(row.get("fields") or {}).get(field)
        if not isinstance(val,str):missing+=1;continue
        key=normalize(val)
        if not re.fullmatch("AMEA[0-9]{8,}(?:[0-9]{2})?",key):missing+=1;continue
        out[key]+=1
    return out,missing
def status(issued,outstanding):
    if issued and outstanding:return "P0_BOTH","Issue invoice and chase payment"
    if issued:return "P1_ETAX","Issue tax invoice"
    if outstanding:return "P1_PAYMENT","Follow up unpaid balance"
    return "REVIEW","Review unmatched record"
def google():
    raw=os.environ.get("GCP_SERVICE_ACCOUNT_JSON","")
    if not raw:raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON_MISSING")
    creds=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(creds)
def api(s,method,suffix,**kw):
    r=s.request(method,"https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+suffix,timeout=45,**kw)
    if not r.ok:raise RuntimeError("SHEETS_HTTP_"+str(r.status_code))
    return r.json() if r.content else {}
def sheet(s,title):
    meta=api(s,"GET","?fields=sheets.properties.title")
    if title not in {x["properties"]["title"] for x in meta.get("sheets",[])}:
        api(s,"POST",":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":title,"gridProperties":{"rowCount":2000,"columnCount":12,"frozenRowCount":1}}}}]})
def values(s,title,range_,rows):
    address=urllib.parse.quote("'"+title+"'!"+range_,safe="")
    api(s,"PUT","/values/"+address+"?valueInputOption=RAW",json={"values":rows})
def main():
    now=dt.datetime.now(KST)
    auth=request("POST","/open-apis/auth/v3/tenant_access_token/internal",body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    if auth.get("code")!=0 or not auth.get("tenant_access_token"):raise RuntimeError("FEISHU_AUTH_FAILED")
    token=auth["tenant_access_token"]
    prefix="/open-apis/bitable/v1/apps/"+urllib.parse.quote(require("FEISHU_BASE_APP_TOKEN"),safe="")
    tables=list(list_pages(prefix+"/tables",token))
    etax,matches=select_etax(tables,now.year,now.month)
    outstanding=[t for t in tables if t.get("name")==OUTSTANDING_TABLE]
    if not etax or matches!=1 or len(outstanding)!=1:raise RuntimeError("FEISHU_SOURCE_AMBIGUOUS")
    def read(table):
        root=prefix+"/tables/"+urllib.parse.quote(table["table_id"],safe="")
        fields=list(list_pages(root+"/fields",token))
        project=pick(fields)
        if not project:raise RuntimeError("PROJECT_COLUMN_NOT_FOUND")
        records=list(list_pages(root+"/records",token))
        return group(records,project),len(records)
    (etax_rows,etax_missing),etax_raw=read(etax)
    (pay_rows,pay_missing),pay_raw=read(outstanding[0])
    if not etax_rows or not pay_rows:raise RuntimeError("EMPTY_FEISHU_SOURCE_REFUSE_OVERWRITE")
    projects=sorted(set(etax_rows)|set(pay_rows))
    time=now.strftime("%Y-%m-%d %H:%M:%S KST")
    output=[HEAD]
    for key in projects:
        issue=key in etax_rows;unpaid=key in pay_rows
        priority,action=status(issue,unpaid)
        output.append([key,"YES" if issue else "NO","YES" if unpaid else "NO",priority,time,etax_rows.get(key,0),pay_rows.get(key,0),"eTAX "+now.strftime("%Y-%m")+" + "+OUTSTANDING_TABLE,"UNVERIFIED",action])
    s=google();sheet(s,"Feishu Project Status");sheet(s,"Automation Health")
    # Snapshot is a generated table; do not clear or mutate historical invoice source tabs.
    values(s,"Feishu Project Status","A1",output)
    # A stable project count or month shift never implies paid or issued; changes require source evidence.
    values(s,"Automation Health","A4",[["Feishu",time,"PASS","projects="+str(len(projects))+" eTAX_records="+str(etax_raw)+" outstanding_records="+str(pay_raw)+" unmatched="+str(etax_missing+pay_missing)]])
    print("FEISHU_PROJECT_SYNC_PASS projects="+str(len(projects))+" overlap="+str(len(set(etax_rows)&set(pay_rows)))+" etax_unmatched="+str(etax_missing)+" pay_unmatched="+str(pay_missing))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("FEISHU_PROJECT_SYNC_FAILED "+type(e).__name__,file=sys.stderr);raise
