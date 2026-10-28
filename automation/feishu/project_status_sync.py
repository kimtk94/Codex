#!/usr/bin/env python3
"""Feishu project-level status -> private unified Sheet. Read-only Feishu, no mail send.

Both eTAX (not issued) and Outstanding (unpaid) are independently retained.
Missing project IDs are excluded and counted; a failed audit cannot erase history.
"""
import datetime as dt
import json, os, re, sys, urllib.parse, time, random
from collections import defaultdict
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
        if isinstance(val,list):
            val=" ".join(str(v.get("text") or v.get("name") or "") if isinstance(v,dict) else str(v) for v in val)
        elif isinstance(val,dict):
            val=val.get("text") or val.get("name") or val.get("value") or ""
        if not isinstance(val,str):missing+=1;continue
        key=normalize(val)
        if len(key)<6 or len(key)>120 or not any(ch.isdigit() for ch in key):missing+=1;continue
        out[key]+=1
    return out,missing
def status(issued,outstanding):
    if issued and outstanding:return "P0_BOTH","Issue invoice and chase payment"
    if issued:return "P1_ETAX","Issue tax invoice"
    if outstanding:return "P1_PAYMENT","Follow up unpaid balance"
    return "REVIEW","Review unmatched record"
def google():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw=os.environ.get("GCP_SERVICE_ACCOUNT_JSON","")
    if not raw:raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON_MISSING")
    creds=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(creds)
def api(s,method,suffix,**kw):
    for attempt in range(7):
        r=s.request(method,"https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+suffix,timeout=45,**kw)
        if r.status_code in (429,500,502,503,504) and attempt<6:
            time.sleep(min(60,2**attempt+random.uniform(0,1)))
            continue
        if not r.ok:raise RuntimeError("SHEETS_HTTP_"+str(r.status_code))
        return r.json() if r.content else {}

def sheet(s,title):
    meta=api(s,"GET","?fields=sheets.properties.title")
    if title not in {x["properties"]["title"] for x in meta.get("sheets",[])}:
        api(s,"POST",":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":title,"gridProperties":{"rowCount":2000,"columnCount":12,"frozenRowCount":1}}}}]})
def values(s,title,range_,rows):
    address=urllib.parse.quote("'"+title+"'!"+range_,safe="")
    api(s,"PUT","/values/"+address+"?valueInputOption=RAW",json={"values":rows})
def latest_flags(snapshots,prior,stamp):
    """Disappearance never means paid/issued; eTax requires explicit status text."""
    projects=defaultdict(lambda:{'tax':False,'pay':False,'etax':0,'out':0})
    aliases={'projectnumber','projectid','ameaprojectid','ameaprojectnumber','projectno','subprojectnumber'}
    for fmt in ('Payment Outstanding','eTax Invoice'):
        item=snapshots[fmt]
        normalized=[re.sub('[^a-z0-9]','',h.lower()) for h in item['headers']]
        columns=[i for i,h in enumerate(normalized) if h in aliases]
        if len(columns)!=1 or item['schema']!='HEADER_MATCHED':continue
        statuses=[i for i,h in enumerate(normalized) if h in {'invoicestatus','taxinvoicestatus','etaxstatus'}]
        for row in item['rows']:
            value=str(row[columns[0]]).strip()
            # Keep identifiers exact (including suffixes); no customer-name joins.
            if not re.fullmatch(r'(?:AMEA|[XH])[-A-Za-z0-9]{5,119}',value,re.I):continue
            key=normalize(value);entry=projects[key]
            if fmt=='Payment Outstanding':entry['pay']=True;entry['out']+=1
            else:
                entry['etax']+=1
                if len(statuses)==1 and str(row[statuses[0]]).strip().lower() in {'unissued','not issued','pending issuance','미발행'}:entry['tax']=True
    for row in prior:
        if row and row[0]:projects.setdefault(row[0],{'tax':False,'pay':False,'etax':0,'out':0})
    result=[HEAD]
    for key,v in sorted(projects.items()):
        priority,action=status(v['tax'],v['pay'])
        if not v['tax'] and not v['pay']:priority='REVIEW_CARRYOVER';action='No settlement/issuance inferred; verify explicit evidence'
        result.append([key,'YES' if v['tax'] else 'UNKNOWN','YES' if v['pay'] else 'UNKNOWN',priority,stamp,v['etax'],v['out'],'Latest Feishu Sheets; see Feishu Source Manifest','UNVERIFIED',action])
    return result

def main():
    from latest_source_sync import collect,publish
    snapshots=collect()  # All five reads and source selection must finish before any writes.
    session=google()
    prior_addr=urllib.parse.quote("'Feishu Project Status'!A2:J10000",safe='')
    meta=api(session,'GET','?fields=sheets.properties.title')
    exists='Feishu Project Status' in {x['properties']['title'] for x in meta.get('sheets',[])}
    prior=api(session,'GET','/values/'+prior_addr).get('values',[]) if exists else []
    stamp=dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')
    output=latest_flags(snapshots,prior,stamp)
    if len(output)>2000:raise RuntimeError('PROJECT_STATUS_CAPACITY_EXCEEDED')
    publish(session,snapshots)
    sheet(session,'Feishu Project Status')
    # Generated status only; existing review and exclusion ledgers are untouched.
    padded=output+[['']*len(HEAD) for _ in range(max(0,len(prior)+1-len(output)))]
    values(session,'Feishu Project Status','A1',padded)
    print('FEISHU_PROJECT_SYNC_PASS projects='+str(len(output)-1)+' source_selection=LATEST_DATED_SHEETS')
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("FEISHU_PROJECT_SYNC_FAILED "+type(e).__name__,file=sys.stderr);sys.exit(1)
