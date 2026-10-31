#!/usr/bin/env python3
"""Build a source-backed AMEA -> H/X/stage candidate review, without changing Watch.

Feishu Online Contract Name is the only available same-row AMEA -> H/X link.
Outstanding/eTax have independent same-row AMEA -> base X links.
No positional join; no inferred Z suffix; no stage/H from finance-only X;
no approval of invoice, revenue, ownership or payment.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB="CSS AMEA Contract Candidate Crosswalk"
KST=ZoneInfo("Asia/Seoul")
AMEA=re.compile(r"AMEA20\d{8}")
X_BASE=re.compile(r"^X[A-Z0-9]{10,30}$",re.I)
STAGE=re.compile(r"^X[A-Z0-9]{10,30}-Z\d{2}-F\d{3}$",re.I)
H_KEY=re.compile(r"^H[A-Z0-9]{10,30}$",re.I)
HEAD=["AMEA","Project / Institution","Watch Quote KRW","Watch X (unsafe)",
      "Online H Candidate","Online X Candidate","Online Stage Candidate",
      "Finance Base X Candidate","Evidence State","Online Rows","Outstanding Rows",
      "eTax Rows","Outstanding Gross KRW","eTax Gross KRW","Source Date Online",
      "Source Date Finance","Attribution Gate","Review Instruction","Checked KST","GitHub Run"]

def cell(row,index):
    return str(row[index]).strip() if row is not None and index<len(row) and row[index] is not None else ""

def xbase(raw):
    val=str(raw or "").strip().upper()
    if not val:return ""
    prefix=val.split("-Z",1)[0]
    if not X_BASE.fullmatch(prefix):raise ValueError("SOURCE_X_FORMAT")
    if val!=prefix and not re.fullmatch(r"^X[A-Z0-9]{10,30}-Z\d{2}(?:-F\d{3})?$",val):
        raise ValueError("SOURCE_X_SUFFIX_FORMAT")
    return prefix

def head(rows,pairs,reason):
    if not rows or any(cell(rows[0],i)!=name for i,name in pairs):
        raise ValueError("SCHEMA_DRIFT_"+reason)

def assess(watch,online,outstanding,etax,manifest,now):
    if now.tzinfo is None:raise ValueError("NAIVE_TIME")
    head(watch,[(0,"AMEA Project ID"),(4,"Quote KRW"),(10,"Review Status"),(13,"X Sub-project")],"WATCH")
    head(online,[(0,"Feishu Record ID"),(1,"Contract Number"),(2,"Sub-Project Number"),
                 (6,"Staging Number"),(17,"Contract Name")],"ONLINE")
    head(outstanding,[(5,"Project Number"),(7,"Quotation Number"),(12,"Invoice Amount")],"OUTSTANDING")
    head(etax,[(9,"Project Number"),(10,"Quotation Number"),(15,"Amount")],"ETAX")
    head(manifest,[(0,"Source"),(1,"Source Date"),(4,"Rows")],"MANIFEST")
    source_rows={
        "Online-Project":online,
        "Payment Outstanding":outstanding,
        "eTax Invoice":etax
    }
    days={}
    for source,rows in source_rows.items():
        items=[r for r in manifest[1:] if cell(r,0)==source]
        if len(items)!=1:raise ValueError("SOURCE_MANIFEST_MISSING_OR_DUPLICATE_"+source)
        try:
            day=dt.date.fromisoformat(cell(items[0],1))
            n=int(cell(items[0],4))
        except ValueError as exc:raise ValueError("SOURCE_MANIFEST_INVALID_"+source) from exc
        if day>now.astimezone(KST).date():raise ValueError("FUTURE_SOURCE_DATE")
        if n!=len(rows)-1:raise ValueError("SOURCE_ROW_DRIFT_"+source)
        days[source]=day
    by_online=collections.defaultdict(list)
    ambiguous_online=set()
    for r in online[1:]:
        found=set(AMEA.findall(cell(r,17)))
        if not found:continue
        if len(found)!=1:
            ambiguous_online.update(found)
            continue
        amea=next(iter(found))
        h,x,z=cell(r,1).upper(),cell(r,2).upper(),cell(r,6).upper()
        if (not H_KEY.fullmatch(h) or not x or not z and not xbase(x)):
            raise ValueError("ONLINE_CONTRACT_OR_X_INVALID")
        xb=xbase(x)
        if z and (not STAGE.fullmatch(z) or xbase(z)!=xb):
            raise ValueError("ONLINE_STAGE_CONFLICT")
        by_online[amea].append((h,x,z,cell(r,0),xb))
    by_finance=collections.defaultdict(list)
    for source,rows,xcol,acol,gcol in (
        ("Outstanding",outstanding,5,7,12),
        ("eTax",etax,9,10,15)):
        for r in rows[1:]:
            amea=cell(r,acol)
            if not AMEA.fullmatch(amea):continue
            raw=cell(r,xcol)
            if not raw:
                by_finance[amea].append((source,"",cell(r,gcol)))
                continue
            by_finance[amea].append((source,xbase(raw),cell(r,gcol)))
    out=[]
    counts=collections.Counter()
    for row in watch[1:]:
        amea=cell(row,0)
        if not amea:continue
        if not AMEA.fullmatch(amea):raise ValueError("WATCH_AMEA_INVALID")
        if cell(row,10)!="ISSUANCE_NOT_VERIFIED":
            raise ValueError("WATCH_ISSUANCE_DECISION_CHANGED")
        online_rows=by_online.get(amea,[])
        finance_rows=by_finance.get(amea,[])
        online_keys={(h,x,z) for h,x,z,_,xb in online_rows}
        finance_x={x for _,x,_ in finance_rows if x}
        online_x={xb for _,_,_,_,xb in online_rows}
        finance_missing=bool(finance_rows and any(not x for _,x,_ in finance_rows))
        if amea in ambiguous_online or len(online_keys)>1:
            state="AMBIGUOUS_ONLINE_CONTRACT_REVIEW"
        elif len(finance_x)>1:
            state="MULTIPLE_FINANCE_X_REVIEW"
        elif online_keys and finance_x and online_x!=finance_x:
            state="ONLINE_FINANCE_X_CONFLICT"
        elif online_keys and finance_x and not finance_missing:
            state="ONLINE_FINANCE_SAME_X_CANDIDATE"
        elif online_keys:
            state="ONLINE_AMEA_CANDIDATE"
        elif finance_x:
            state="FINANCE_AMEA_CANDIDATE"
        else:
            state="NO_AMEA_SOURCE_CANDIDATE"
        has_unique_online=bool(len(online_keys)==1 and amea not in ambiguous_online)
        online_single=next(iter(online_keys)) if has_unique_online else ("","","")
        finance_single=next(iter(finance_x)) if len(finance_x)==1 else ""
        unsafe=cell(row,13)
        if len(online_rows)!=len({r[3] for r in online_rows}):
            raise ValueError("ONLINE_SOURCE_DUPLICATE_RECORD")
        source_derived=state in {
            "ONLINE_FINANCE_SAME_X_CANDIDATE",
            "ONLINE_AMEA_CANDIDATE",
            "FINANCE_AMEA_CANDIDATE"}
        gate="CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW" if source_derived else "QUARANTINE_NO_CONTRACT_ATTRIBUTION"
        desc=("Original AMEA evidence only. Do not infer H/Z/stage from finance base X; "
              "check institution and original contract/PDF; do not certify issued, paid, or Revenue Actual.")
        if source_derived and finance_x and any((now.astimezone(KST).date()-days[x]).days>2
                                                for x in ("Payment Outstanding","eTax Invoice")):
            desc+=" Finance snapshot is older than 2 days."
        if unsafe and (not has_unique_online or unsafe!=online_single[1]):
            desc+=" Watch X is an independent positional join and is not an authority."
        def amount(source):
            vals=[v for kind,_,v in finance_rows if kind==source]
            if not vals:return ""
            if any(not re.fullmatch(r"\d+",v.replace(",","")) for v in vals):
                raise ValueError("FINANCE_AMOUNT_INVALID")
            return sum(int(v.replace(",","")) for v in vals)
        out.append([amea,cell(row,1),cell(row,4),unsafe,
                    online_single[0] if has_unique_online else "",
                    online_single[1] if has_unique_online else "",
                    online_single[2] if has_unique_online else "",
                    finance_single,state,len(online_rows),
                    sum(kind=="Outstanding" for kind,_,_ in finance_rows),
                    sum(kind=="eTax" for kind,_,_ in finance_rows),
                    amount("Outstanding"),amount("eTax"),
                    days["Online-Project"].isoformat(),
                    min(days["Payment Outstanding"],days["eTax Invoice"]).isoformat(),
                    gate,desc,now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST"),""])
        counts[state]+=1
    if not out:raise ValueError("NO_WATCH_PROJECTS")
    if len({r[0] for r in out})!=len(out):raise ValueError("WATCH_DUPLICATE_AMEA")
    return out,{"watch_projects":len(out),"state_counts":dict(sorted(counts.items())),
                "candidate_rows":sum(n for k,n in counts.items() if k in {
                   "ONLINE_FINANCE_SAME_X_CANDIDATE","ONLINE_AMEA_CANDIDATE","FINANCE_AMEA_CANDIDATE"}),
                "source_dates":{s:d.isoformat() for s,d in days.items()},
                "original_source_writes":0,"revenue_writes":0,"issued_or_paid_certified":0}

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    run=os.getenv("GITHUB_RUN_ID","")
    token=os.getenv("CKD_DRIVE_SA_JSON","")
    if not token or not run.isdigit() or os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("UNTRUSTED_ACTION_CONTEXT")
    session=AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(token),scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    root="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    def req(method,url,**kwargs):
        response=session.request(method,url,timeout=60,**kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    def read(tab,rng):
        return req("GET",root+"/values/"+quote("'"+tab+"'!"+rng,safe="")).get("values",[])
    rows,summary=assess(
        read("Unissued Invoice Watch","A1:O500"),
        read("Feishu Latest Online","A1:Z250"),
        read("Feishu Latest Outstanding","A1:N500"),
        read("Feishu Latest eTax","A1:Z250"),
        read("Feishu Source Manifest","A1:G20"),
        dt.datetime.now(KST))
    if len(rows)>300:raise RuntimeError("REVIEW_CAPACITY")
    meta=req("GET",root,params={"fields":"sheets.properties(title,sheetId)"})
    if not any(r.get("properties",{}).get("title")==TAB for r in meta.get("sheets",[])):
        req("POST",root+":batchUpdate",json={"requests":[{"addSheet":{"properties":{
            "title":TAB,"gridProperties":{"rowCount":400,"columnCount":len(HEAD),
                                           "frozenRowCount":1}}}}]})
    old=req("GET",root+"/values/"+quote("'"+TAB+"'!A1:T1",safe="")).get("values",[])
    if old and old[0]!=HEAD:raise RuntimeError("REFUSE_FOREIGN_CROSSWALK_TAB")
    dest=root+"/values/"+quote("'"+TAB+"'!A1:T"+str(len(rows)+1),safe="")
    output=[HEAD]+[r[:-1]+["https://github.com/kimtk94/Codex/actions/runs/"+run] for r in rows]
    # One idempotent update; no deletion of manually maintained business inputs.
    req("PUT",dest,params={"valueInputOption":"RAW"},json={"values":output})
    back=req("GET",dest).get("values",[])
    def normalized(matrix):
        return [[str(v) if v is not None else "" for v in r] for r in matrix]
    if normalized(back)!=normalized(output):
        raise RuntimeError("CROSSWALK_READBACK_MISMATCH")
    print("CSS_AMEA_CONTRACT_CANDIDATES="+json.dumps(summary,sort_keys=True))
    print("ORIGINAL_WATCH_UNCHANGED;NO_REVENUE_BOOKING;NO_ISSUANCE_OR_PAYMENT_CLAIM")

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("CSS_AMEA_CROSSWALK_FAILED="+type(error).__name__,file=sys.stderr)
        sys.exit(1)
