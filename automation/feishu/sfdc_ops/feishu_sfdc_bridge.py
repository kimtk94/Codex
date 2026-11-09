#!/usr/bin/env python3
"""Feishu Base <-> private Google Sheets SFDC queue bridge, no CRM credentials.

Two jobs: bootstrap (idempotently add a named operations table), sync (copy
validated UI requests into private queue and mirror completed execution results).
Neither can access Salesforce. The desktop worker alone owns Salesforce UI.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.parse as up
import urllib.request as ur

BASE_URL = "https://open.feishu.cn"
TABLE_NAME = "SFDC 업무요청"
SOURCE_BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
QUEUE_TAB = "SFDC Feishu Queue"
RESULTS_TAB = "SFDC Feishu Results"
FIELDS = [
    ("요청 ID", 1), ("기능", 3), ("요청", 3), ("원본 ID", 1),
    ("원본 Quote ID", 1), ("새 이름", 1), ("기관", 1),
    ("담당 Contact", 1), ("샘플 수", 2), ("샘플당 Gb", 2),
    ("마감일", 1), ("신규 Progress Description", 1),
    ("가격 확인", 7), ("중복 확인", 7), ("실제 저장 승인", 7),
    ("실행 상태", 1), ("예상 공급가 KRW", 2), ("예상 VAT KRW", 2),
    ("새 Oppo ID", 1), ("새 Quote ID", 1), ("오류 코드", 1),
    ("검증 시각", 1), ("요청 지문", 1),
]
OPTIONS = {
    "기능": ["Lead Convert", "Oppo + Quote", "Opportunity", "Quote"],
    "요청": ["DRAFT", "PREFLIGHT", "SAVE"],
}
QUEUE_COLUMNS = ["record_id", "request_id", "fingerprint", "action", "mode",
                 "source_id", "source_quote_id", "new_name", "institution",
                 "contact", "samples", "gb_per_sample", "close_date",
                 "progress", "price_confirmed", "duplicate_confirmed",
                 "save_approved", "source_created_at"]
RESULT_COLUMNS = ["record_id", "request_id", "fingerprint", "status", "code",
                  "expected_net_krw", "expected_vat_krw", "new_oppo_id",
                  "new_quote_id", "checked_at", "local_provenance"]
STATUS_ALLOWED = {"QUEUED", "PREFLIGHT_PASS", "BLOCK", "PARTIAL", "SAVE_SUBMITTED_READBACK_REQUIRED", "PASS"}
ACTION_MAP = {"Lead Convert": "lead_convert", "Oppo + Quote": "oppo_quote_pair",
              "Opportunity": "opportunity_create", "Quote": "quote_create"}


def request(method, url, token=None, body=None):
    headers={"Content-Type":"application/json"}
    if token: headers["Authorization"]="Bearer "+token
    data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
    req=ur.Request(url,data=data,headers=headers,method=method)
    with ur.urlopen(req,timeout=32) as res:
        obj=json.load(res)
    if not isinstance(obj,dict) or obj.get("code") != 0:
        raise RuntimeError("FEISHU_API_REJECTED")
    if url.endswith("/tenant_access_token/internal"):
        return obj
    return obj.get("data") or {}


def auth():
    aid=os.environ.get("FEISHU_APP_ID","")
    secret=os.environ.get("FEISHU_APP_SECRET","")
    app=os.environ.get("FEISHU_BASE_APP_TOKEN","")
    if not all((aid,secret,app)): raise RuntimeError("FEISHU_CREDENTIALS_UNAVAILABLE")
    result=request("POST", BASE_URL+"/open-apis/auth/v3/tenant_access_token/internal",
                   body={"app_id":aid,"app_secret":secret})
    token=result.get("tenant_access_token")
    if not token:raise RuntimeError("FEISHU_AUTH_FAIL")
    return token, app


def paginate(url,token):
    items=[];cursor=""
    while True:
        sep="&" if "?" in url else "?"
        page=url+sep+up.urlencode({"page_size":100,**({"page_token":cursor} if cursor else {})})
        data=request("GET",page,token)
        items.extend(data.get("items") or [])
        if not data.get("has_more"):return items
        newer=data.get("page_token")
        if not newer or newer==cursor:raise RuntimeError("FEISHU_PAGINATION_INVALID")
        cursor=newer
        if len(items)>20000:raise RuntimeError("FEISHU_PAGINATION_LIMIT")


def url_base(app):return BASE_URL+"/open-apis/bitable/v1/apps/"+up.quote(app,safe="")

def field_specs():
    result=[]
    for name,type_id in FIELDS:
        row={"field_name":name,"type":type_id}
        if name in OPTIONS:
            row["property"]={"options":[{"name":v} for v in OPTIONS[name]]}
        result.append(row)
    return result


def find_table(token,app):
    rows=paginate(url_base(app)+"/tables",token)
    matches=[r for r in rows if r.get("name")==TABLE_NAME]
    if len(matches)>1:raise RuntimeError("FEISHU_DUPLICATE_TABLE")
    return matches[0] if matches else None


def ensure_table(token,app,write):
    table=find_table(token,app)
    if not table and not write:raise RuntimeError("TABLE_MISSING_DRY_RUN")
    created=False
    if not table:
        result=request("POST",url_base(app)+"/tables",token,{"table":{
            "name":TABLE_NAME,"default_view_name":"작업 목록", "fields":field_specs()}})
        table={"table_id":result.get("table_id")}
        created=True
    table_id=table.get("table_id")
    if not table_id:raise RuntimeError("TABLE_ID_UNAVAILABLE")
    path=url_base(app)+"/tables/"+up.quote(table_id,safe="")
    fields=paginate(path+"/fields",token)
    have={f.get("field_name"):f.get("type") for f in fields}
    for name,t in FIELDS:
        if name not in have or have[name]!=t:
            raise RuntimeError("FEISHU_FIELD_SCHEMA_MISMATCH")
    # Form view is the Feishu-native input UI; normal Grid remains the log.
    form_created=False
    if write:
        views=paginate(path+"/views",token)
        if not any(v.get("view_name")=="SFDC 요청 입력" for v in views):
            try:
                request("POST",path+"/views",token,{"view_name":"SFDC 요청 입력","view_type":"form"})
                form_created=True
            except RuntimeError:
                # Grid is still usable; no silent claim of form availability.
                pass
    return table_id,created,form_created


def text_field(v):
    if v is None:return ""
    if isinstance(v,str):return v.strip()
    if isinstance(v,(int,float)) and not isinstance(v,bool):return str(v)
    if isinstance(v,list):return "".join(str(x.get("text", "")) if isinstance(x,dict) else str(x) for x in v).strip()
    return ""


def valid_id(prefix,val):
    return bool(re.fullmatch(re.escape(prefix)+r"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",val))


def normalized_fields(raw):
    return {key:text_field(value) if key not in ("가격 확인","중복 확인","실제 저장 승인") else value is True
            for key,value in raw.items()}


def validate_request(rec):
    """Return safe queue row or None; rows with invalid instructions are ignored."""
    record_id=rec.get("record_id")
    f=normalized_fields(rec.get("fields") or {})
    action=ACTION_MAP.get(f.get("기능"))
    mode=f.get("요청")
    if mode not in ("PREFLIGHT","SAVE") or not action:return None
    request_id=f.get("요청 ID","")
    if not re.fullmatch(r"SFDC-[A-Z0-9-]{8,48}",request_id):return None
    src=f.get("원본 ID","")
    prefix={"lead_convert":"00Q","oppo_quote_pair":"006",
            "opportunity_create":"006","quote_create":"a0P"}[action]
    if not valid_id(prefix,src):return None
    quote=f.get("원본 Quote ID","")
    if quote and not valid_id("a0P",quote):return None
    if not isinstance(record_id,str) or not re.fullmatch(r"rec[A-Za-z0-9]{7,32}",record_id):return None
    samples_raw=f.get("샘플 수","")
    size_raw=f.get("샘플당 Gb","")
    try:
        samples=int(float(samples_raw)) if samples_raw else 0
        gb=float(size_raw) if size_raw else 0
        if samples_raw and float(samples_raw)!=samples: return None
    except (TypeError,ValueError):return None
    if action!="lead_convert" and not(1<=samples<=500 and 0<gb<=100000):return None
    if action=="lead_convert": samples=0;gb=0
    title=f.get("새 이름","")
    if action!="lead_convert" and not(5<=len(title)<=230):return None
    if len(f.get("기관", ""))>150 or len(f.get("담당 Contact",""))>150:return None
    if len(f.get("신규 Progress Description",""))>2000:return None
    progress=f.get("신규 Progress Description","")
    if action in ("oppo_quote_pair","opportunity_create") and len(progress)<15:return None
    close=f.get("마감일","")
    if close and not re.fullmatch(r"\d{4}-\d{2}-\d{2}",close):return None
    approved=bool(f.get("실제 저장 승인"))
    dup=bool(f.get("중복 확인"))
    price=bool(f.get("가격 확인"))
    # Never accept a SAVE that is not separately attested by the user.
    if mode=="SAVE" and not (approved and dup and price):return None
    # Stable request payload hash across PREFLIGHT -> SAVE. Exclude approvals and mode.
    values=[action,src,quote,title,f.get("기관",""),f.get("담당 Contact",""),
            samples,gb,close,progress]
    fingerprint=hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return [record_id,request_id,fingerprint,action,mode,src,quote,title,
            f.get("기관",""),f.get("담당 Contact",""),str(samples),str(gb),close,
            progress,str(price).lower(),str(dup).lower(),str(approved).lower(),
            str(rec.get("created_time") or "")]


def pure_reconcile(requests,results):
    """Only matching fingerprint + record ID can be echoed to Feishu."""
    current={r[0]:(r[1],r[2],r[4]) for r in requests}
    seen=set();out=[]
    for row in results:
        if len(row)<len(RESULT_COLUMNS):continue
        rid,req,fingerprint,status=row[:4]
        if not rid or rid in seen or current.get(rid)!=(req,fingerprint,row[10]):continue
        if status=="PREFLIGHT_PASS" and row[10]!="PREFLIGHT":continue
        if status=="PASS" and row[10]!="SAVE":continue
        if status not in STATUS_ALLOWED:continue
        seen.add(rid)
        status_fields={"실행 상태":status,"오류 코드":row[4],"검증 시각":row[9],"요청 지문":fingerprint}
        if row[5]:
            try:status_fields["예상 공급가 KRW"]=int(row[5])
            except ValueError:pass
        if row[6]:
            try:status_fields["예상 VAT KRW"]=int(row[6])
            except ValueError:pass
        if valid_id("006",row[7]):status_fields["새 Oppo ID"]=row[7]
        if valid_id("a0P",row[8]):status_fields["새 Quote ID"]=row[8]
        out.append({"record_id":rid,"fields":status_fields})
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=("bootstrap","scan"))
    parser.add_argument("--write",action="store_true")
    args=parser.parse_args()
    try:
        token,app=auth()
        table_id,created,form_created=ensure_table(token,app,args.write)
        base=url_base(app)+"/tables/"+up.quote(table_id,safe="")
        result={"status":"PASS","table_created":created,
                "table_name":TABLE_NAME,"table_id":table_id,"form_created":form_created,
                "write_enabled":args.write}
        if args.command=="scan":
            records=paginate(base+"/records",token)
            valid=[v for rec in records if (v:=validate_request(rec))]
            result.update({"records_read":len(records),"queue_eligible":len(valid)})
        print(json.dumps(result,sort_keys=True,ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({"status":"BLOCK","error_type":type(exc).__name__,
                          "error_message_suppressed":True},sort_keys=True))
        sys.exit(2)

if __name__=="__main__":main()
