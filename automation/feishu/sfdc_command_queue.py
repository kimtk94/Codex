#!/usr/bin/env python3
"""Feishu private Base command inbox -> Google Sheets mirror and result return."""
import os,json,sys,urllib.request,urllib.parse,urllib.error,datetime as dt

TABLE="SFDC_COMMAND_QUEUE"
SHEET="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB="CSS SFDC Command Queue"
FIELDS=["Request ID","Action","Source Oppo ID","Source Quote ID","Lead ID",
"New Opportunity Name","New Samples","Data Size Gb","Account Name",
"Contact Korean Name","Contact English Name","Approval","Duplicate Checked",
"Price Checked","Run Mode","Status","New Oppo ID","New Quote ID",
"New Contact ID","Error Code","Checked At"]
HEAD=["record_id"]+FIELDS
FINAL={"RUNNING","PREFLIGHT_PASS","PREPARED","PREFLIGHT_BLOCK","SAVE_APPROVED",
       "PASS","PARTIAL","BLOCK","SOURCE_UNAVAILABLE"}
def env(key):
    v=os.getenv(key,"").strip()
    if not v:raise ValueError("MISSING_"+key)
    return v
def call(method,path,token="",payload=None):
    headers={"Content-Type":"application/json"}
    if token:headers["Authorization"]="Bearer "+token
    req=urllib.request.Request("https://open.feishu.cn"+path,
        headers=headers,method=method,
        data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None)
    with urllib.request.urlopen(req,timeout=35) as res:result=json.load(res)
    if result.get("code")!=0:raise ValueError("FEISHU_API_"+str(result.get("code")))
    return result.get("data") or result
def auth():
    data=call("POST","/open-apis/auth/v3/tenant_access_token/internal",
        payload={"app_id":env("FEISHU_APP_ID"),"app_secret":env("FEISHU_APP_SECRET")})
    if not data.get("tenant_access_token"):raise ValueError("FEISHU_AUTH_UNAVAILABLE")
    return data["tenant_access_token"]
def path():
    return "/open-apis/bitable/v1/apps/"+urllib.parse.quote(env("FEISHU_BASE_APP_TOKEN"),safe="")
def pages(token,endpoint):
    result=[];cursor=""
    for i in range(100):
        qs=urllib.parse.urlencode({"page_size":100,**({"page_token":cursor} if cursor else {})})
        d=call("GET",endpoint+"?"+qs,token)
        result.extend(d.get("items") or [])
        if not d.get("has_more"):return result
        nxt=d.get("page_token")
        if not nxt or nxt==cursor:raise ValueError("INVALID_PAGINATION")
        cursor=nxt
    raise ValueError("PAGINATION_LIMIT")
def schema(token):
    root=path()
    found=[v for v in pages(token,root+"/tables") if v.get("name")==TABLE]
    if len(found)>1:raise ValueError("DUPLICATE_TABLE")
    if not found:
        call("POST",root+"/tables",token,{"table":{"name":TABLE,
             "default_view_name":"SFDC Requests",
             "fields":[{"field_name":name,"type":1} for name in FIELDS]}})
        found=[v for v in pages(token,root+"/tables") if v.get("name")==TABLE]
    if len(found)!=1:raise ValueError("TABLE_NOT_CREATED")
    tid=found[0]["table_id"]
    fp=root+"/tables/"+tid+"/fields"
    names={v.get("field_name"):v.get("type") for v in pages(token,fp)}
    for name in FIELDS:
        if name not in names:
            call("POST",fp,token,{"field_name":name,"type":1})
    names={v.get("field_name"):v.get("type") for v in pages(token,fp)}
    if any(names.get(n)!=1 for n in FIELDS):raise ValueError("SCHEMA_UNEXPECTED")
    return tid
def plain(v):
    if v is None:return ""
    if isinstance(v,str):return v.strip()
    if isinstance(v,list):
        return "".join(plain(x.get("text","") if isinstance(x,dict) else x) for x in v)
    return str(v).strip()
def normalized(rec):
    rid=rec.get("record_id")
    if not rid:raise ValueError("MISSING_RECORD_ID")
    f=rec.get("fields") or {}
    return [rid]+[plain(f.get(k)) for k in FIELDS]
def eligible(row):
    r=dict(zip(HEAD,row))
    if r.get("Action") not in ("LEAD_CONVERT","OPPO_QUOTE_PAIR") or r.get("Status") not in ("","NEW","QUEUED","REQUESTED"):return False
    if r.get("Run Mode")=="CHECK":return r.get("Approval")=="PREFLIGHT"
    if r.get("Run Mode")=="SAVE":
        return all(r.get(k)==v for k,v in
            (("Approval","APPROVED"),("Duplicate Checked","YES"),("Price Checked","YES")))
    return False
def google():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    c=Credentials.from_service_account_info(json.loads(env("GCP_SERVICE_ACCOUNT_JSON")),
       scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(c)
def gs(s,method,suffix,body=None):
    r=s.request(method,"https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+suffix,
       json=body,timeout=45)
    if not r.ok:raise ValueError("SHEETS_HTTP_"+str(r.status_code))
    return r.json()
def adr(region):
    return urllib.parse.quote("'"+TAB+"'!"+region,safe="!'")
def ensure_mirror(s):
    d=gs(s,"GET","?fields=sheets.properties(title,gridProperties(rowCount,columnCount))")
    tabs={x["properties"]["title"]:x["properties"]["gridProperties"] for x in d.get("sheets",[])}
    if TAB not in tabs:
        gs(s,"POST",":batchUpdate",{"requests":[{"addSheet":{"properties":{"title":TAB,
            "gridProperties":{"rowCount":2000,"columnCount":len(HEAD),"frozenRowCount":1}}}}]})
    elif tabs[TAB]["rowCount"]<1000 or tabs[TAB]["columnCount"]<len(HEAD):
        raise ValueError("SHEET_GRID_SMALL")
def mirror(s):
    rows=gs(s,"GET","/values/"+adr("A1:V2000")).get("values",[])
    if rows and rows[0]!=HEAD:raise ValueError("SHEET_SCHEMA_MISMATCH")
    return {r[0]:r for r in rows[1:] if r and r[0]}
def pull(token,s,tid):
    records=pages(token,path()+"/tables/"+tid+"/records")
    rows=[normalized(x) for x in records]
    if len(rows)>1800 or len(set(r[0] for r in rows))!=len(rows):
        raise ValueError("DUPLICATE_OR_EXCESS_RECORDS")
    keyed=[r[HEAD.index("Request ID")] for r in rows if eligible(r)]
    if not all(keyed) or len(set(keyed))!=len(keyed):
        raise ValueError("DUPLICATE_OR_EMPTY_REQUEST_ID")
    prior=mirror(s)
    if set(prior)-set(r[0] for r in rows):
        raise ValueError("SOURCE_RECORD_DISAPPEARED")
    for row in rows:
        old=dict(zip(HEAD,prior.get(row[0],[])))
        if old.get("Status") in FINAL:
            for field in ("Status","New Oppo ID","New Quote ID","New Contact ID",
                          "Error Code","Checked At"):
                row[HEAD.index(field)]=old.get(field,"")
    values=[HEAD]+rows
    gs(s,"PUT","/values/"+adr("A1:V"+str(len(values)))+"?valueInputOption=RAW",
       {"values":values})
    actual=gs(s,"GET","/values/"+adr("A1:V"+str(len(values)))).get("values",[])
    norm=lambda row:list(row[:next((i for i in range(len(row)-1,-1,-1) if str(row[i])!=""),-1)+1])
    if [norm(v) for v in actual]!=[norm(v) for v in values]:
        raise ValueError("SINK_READBACK_MISMATCH")
    return {"mode":"pull","status":"PASS","requests":len(rows),
            "eligible":sum(eligible(r) for r in rows),"sink_readback":"PASS"}
def push(token,s,tid):
    rows=mirror(s)
    endpoint=path()+"/tables/"+tid+"/records"
    before={r["record_id"]:r for r in pages(token,endpoint)}
    changed=0
    for rid,row in rows.items():
        if rid not in before:continue
        fields=dict(zip(HEAD,row))
        if fields.get("Status") not in FINAL:continue
        update={k:fields.get(k,"") for k in ("Status","New Oppo ID","New Quote ID",
                      "New Contact ID","Error Code","Checked At")}
        if all(plain(before[rid].get("fields",{}).get(k))==v for k,v in update.items()):
            continue
        call("PUT",endpoint+"/"+urllib.parse.quote(rid,safe=""),token,{"fields":update})
        changed+=1
    after={r["record_id"]:r for r in pages(token,endpoint)}
    for rid,row in rows.items():
        f=dict(zip(HEAD,row))
        if rid in after and f.get("Status") in FINAL and plain(after[rid]["fields"].get("Status"))!=f["Status"]:
            raise ValueError("FEISHU_READBACK_MISMATCH")
    return {"mode":"push","status":"PASS","updated":changed,
            "records":len(rows),"feishu_readback":"PASS"}
def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "pull"
    if mode not in ("bootstrap","pull","push"):raise SystemExit(2)
    try:
        token=auth();tid=schema(token)
        if mode=="bootstrap":out={"mode":mode,"status":"PASS","table_id":tid}
        else:
            s=google();ensure_mirror(s)
            out=pull(token,s,tid) if mode=="pull" else push(token,s,tid)
        print(json.dumps(out,sort_keys=True))
    except Exception as exc:
        safe=("FEISHU_HTTP_"+str(exc.code)) if isinstance(exc,urllib.error.HTTPError) else (str(exc) if isinstance(exc,ValueError) and __import__("re").fullmatch(r"[A-Z][A-Z0-9_]{4,95}",str(exc)) else "API_OR_TRANSPORT_FAILURE")
        print(json.dumps({"status":"BLOCK","error_type":type(exc).__name__,
                          "reason":safe,"mode":mode}),file=sys.stderr)
        sys.exit(2)
if __name__=="__main__":main()
