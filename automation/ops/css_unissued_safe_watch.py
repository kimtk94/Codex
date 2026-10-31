#!/usr/bin/env python3
"""Materialize an AMEA-joined, unissued-project SAFE display view, never a billing ledger.

Inputs:
  Unissued Invoice Watch A:K only (never copy its unsafe positional M:W spill).
  CSS AMEA Contract Candidate Crosswalk A:T (generated and keyed by AMEA).
Output:
  CSS Unissued Safe Watch (generated only, no source/Revenue modifications).
No contract is approved from evidence candidates.
"""
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo
from css_amea_contract_candidate_crosswalk import HEAD as CROSSWALK_HEAD, BOOK

KST=ZoneInfo("Asia/Seoul")
TAB="CSS Unissued Safe Watch"
WATCH_HEADER=["AMEA Project ID","Project / Institution / Service","Forecast Month",
              "Estimated Completion","Quote KRW","Quote K USD","Matched Invoice Count",
              "Forecast Status","TAT Basis","Source","Review Status"]
HEAD=["AMEA","Project / Institution / Service","Forecast Month","Estimated Completion",
      "Quote KRW","Quote K USD","Matched Invoice Count","Forecast Status",
      "TAT Basis","Source","Watch Review Status","Approved H Contract",
      "Approved X Sub-project","Approved Stage","Online H Candidate",
      "Online X Candidate","Online Stage Candidate","Finance Base X Candidate",
      "Contract Evidence State","Contract Attribution Gate","Invoice/Payment Gate",
      "Online Source Date","Finance Source Date","Crosswalk Checked KST","GitHub Run"]
CANDIDATES={"ONLINE_FINANCE_SAME_X_CANDIDATE","ONLINE_AMEA_CANDIDATE",
            "FINANCE_AMEA_CANDIDATE"}
VALID_STATES=CANDIDATES|{"NO_AMEA_SOURCE_CANDIDATE","AMBIGUOUS_ONLINE_CONTRACT_REVIEW",
 "MULTIPLE_FINANCE_X_REVIEW","ONLINE_FINANCE_X_CONFLICT","X_REFERENCES_MULTIPLE_AMEAS"}
X_RE=re.compile(r"^X[A-Z0-9]{10,30}(?:-Z\d{2})?$",re.I)
H_RE=re.compile(r"^H[A-Z0-9]{10,30}$",re.I)
AMEA_RE=re.compile(r"^AMEA20\d{8}$")

def val(row,i):
    return str(row[i]).strip() if i<len(row) and row[i] is not None else ""

def int_amount(v):
    v=str(v).replace(",","").strip()
    if not re.fullmatch(r"\d+",v):
        raise ValueError("BAD_QUOTE_AMOUNT")
    return int(v)

def checked_at(raw):
    return dt.datetime.strptime(raw,"%Y-%m-%d %H:%M:%S KST").replace(tzinfo=KST)

def project(watch,crosswalk,now):
    """Pure fail-closed transformation. Preserve quotes, never propagate legacy H/X."""
    if now.tzinfo is None: raise ValueError("NAIVE_TIME")
    if not watch or [val(watch[0],i) for i in range(len(WATCH_HEADER))]!=WATCH_HEADER:
        raise ValueError("WATCH_SCHEMA_CHANGED")
    if not crosswalk or [val(crosswalk[0],i) for i in range(len(CROSSWALK_HEAD))]!=CROSSWALK_HEAD:
        raise ValueError("CROSSWALK_SCHEMA_CHANGED")
    index={}
    for r in crosswalk[1:]:
        a=val(r,0)
        if not a:continue
        if not AMEA_RE.fullmatch(a) or a in index:
            raise ValueError("CROSSWALK_AMEA_DUPLICATE_OR_INVALID")
        state,gate=val(r,8),val(r,16)
        if state not in VALID_STATES:raise ValueError("UNKNOWN_CROSSWALK_STATE")
        candidate=state in CANDIDATES
        if gate!=("CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW" if candidate else
                 "QUARANTINE_NO_CONTRACT_ATTRIBUTION"):
            raise ValueError("CONTRACT_GATE_CONTRADICTION")
        age=(now.astimezone(KST)-checked_at(val(r,18))).total_seconds()
        if age<0 or age>36*3600:raise ValueError("CROSSWALK_STALE_OR_FUTURE")
        online_x=val(r,5)
        finance_x=val(r,7)
        if candidate:
            if state=="FINANCE_AMEA_CANDIDATE":
                if online_x or not finance_x or not X_RE.fullmatch(finance_x) or "-Z" in finance_x:
                    raise ValueError("FINANCE_CANDIDATE_INVALID")
            elif not online_x or not X_RE.fullmatch(online_x) or "-Z" not in online_x:
                raise ValueError("ONLINE_CANDIDATE_INVALID")
        if state=="ONLINE_FINANCE_SAME_X_CANDIDATE":
            if online_x.split("-")[0]!=finance_x:raise ValueError("CANDIDATE_CROSS_SOURCE_MISMATCH")
        online_day=dt.date.fromisoformat(val(r,14))
        finance_day=dt.date.fromisoformat(val(r,15))
        if online_day>now.astimezone(KST).date() or finance_day>now.astimezone(KST).date():
            raise ValueError("FUTURE_SOURCE_DATE")
        index[a]=(r,state,gate,candidate)
    out=[]
    used=set()
    for w in watch[1:]:
        a=val(w,0)
        if not a:continue
        if not AMEA_RE.fullmatch(a) or a in used:raise ValueError("WATCH_AMEA_DUPLICATE")
        if a not in index:raise ValueError("CROSSWALK_MISSING_AMEA")
        r,state,gate,candidate=index[a]
        if val(w,1)!=val(r,1) or int_amount(val(w,4))!=int_amount(val(r,2)):
            raise ValueError("PROJECT_OR_QUOTE_MISMATCH")
        if val(w,10)!="ISSUANCE_NOT_VERIFIED":
            raise ValueError("WATCH_ISSUANCE_STATE_CHANGED")
        if candidate and val(r,4) and not H_RE.fullmatch(val(r,4)):
            raise ValueError("ONLINE_H_INVALID")
        # Approved columns (L:M:N) MUST stay blank until an independent
        # authenticated contract/PDF approval workflow exists.
        online_h=val(r,4) if candidate else ""
        online_x=val(r,5) if candidate else ""
        stage=val(r,6) if candidate else ""
        finance_x=val(r,7) if candidate else ""
        out.append([a]+[val(w,i) for i in range(1,11)]+
                   ["","","",online_h,online_x,stage,finance_x,state,gate,
                    "ISSUANCE_NOT_VERIFIED;PAYMENT_NOT_VERIFIED",val(r,14),val(r,15),
                    val(r,18),""])
        used.add(a)
    if not out or len(used)!=len(index):
        raise ValueError("WATCH_CROSSWALK_SET_MISMATCH")
    return out,{"projects":len(out),
                "candidate_only":sum(row[18] in CANDIDATES for row in out),
                "quarantined":sum(row[18] not in CANDIDATES for row in out),
                "approved_contracts":0,"approved_invoices":0,"source_writes":0}

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    run=os.getenv("GITHUB_RUN_ID","")
    token=os.getenv("CKD_DRIVE_SA_JSON","")
    if not token or not run.isdigit() or os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("UNTRUSTED_ACTION_CONTEXT")
    sess=AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(token),scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    root="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    def req(method,url,**kwargs):
        response=sess.request(method,url,timeout=60,**kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    def read(tab,rng):
        return req("GET",root+"/values/"+quote("'"+tab+"'!"+rng,safe="")).get("values",[])
    rows,summary=project(
        read("Unissued Invoice Watch","A1:K500"),
        read("CSS AMEA Contract Candidate Crosswalk","A1:T500"),
        dt.datetime.now(KST))
    if len(rows)>300:raise RuntimeError("SAFE_WATCH_CAPACITY")
    rows=[r[:-1]+["https://github.com/kimtk94/Codex/actions/runs/"+run] for r in rows]
    meta=req("GET",root,params={"fields":"sheets.properties(title,sheetId,gridProperties(rowCount,columnCount))"})
    props={x["properties"]["title"]:x["properties"] for x in meta.get("sheets",[])}
    if TAB in props and props[TAB].get("gridProperties",{}).get("columnCount",0)<len(HEAD):
        raise RuntimeError("SAFE_WATCH_COLUMN_CAPACITY")
    if TAB in props and props[TAB].get("gridProperties",{}).get("rowCount",0)<400:
        req("POST",root+":batchUpdate",json={"requests":[{"updateSheetProperties":{
            "properties":{"sheetId":props[TAB]["sheetId"],
                          "gridProperties":{"rowCount":400}},
            "fields":"gridProperties.rowCount"}}]})
    if TAB not in props:
        req("POST",root+":batchUpdate",json={"requests":[{"addSheet":{"properties":{
          "title":TAB,"gridProperties":{"rowCount":400,"columnCount":len(HEAD),
          "frozenRowCount":1}}}}]})
    check=read(TAB,"A1:Y1")
    if check and check[0]!=HEAD:raise RuntimeError("SAFE_WATCH_FOREIGN_TAB")
    output=[HEAD]+rows
    # Replace generated-only data; blank trailing rows from previous larger runs.
    dest=root+"/values/"+quote("'"+TAB+"'!A1:Y400",safe="")
    padded=output+[[""]*len(HEAD) for _ in range(400-len(output))]
    req("PUT",dest,params={"valueInputOption":"RAW"},json={"values":padded})
    verified=read(TAB,"A1:Y"+str(len(output)))
    def normalize(matrix):return [[str(x) if x is not None else "" for x in r] for r in matrix]
    if normalize(verified)!=normalize(output):raise RuntimeError("SAFE_WATCH_READBACK_MISMATCH")
    print("CSS_UNISSUED_SAFE_WATCH="+json.dumps(summary,sort_keys=True))
    print("LEGACY_WATCH_A_K_PRESERVED;LEGACY_H_X_M_W_IGNORED;APPROVED_H_X_STAGE_BLANK")
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CSS_UNISSUED_SAFE_WATCH_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
