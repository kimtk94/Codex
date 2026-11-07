#!/usr/bin/env python3
"""Read-only bridge audit: current SFDC Quotation process report vs approval evidence.

The Quotation report has PRODUCT rows, not one row per quote. A value is only
a candidate when all rows for one exact QID agree on Active, USD total,
currency and Opportunity. No records are written or auto-merged.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
REQUIRED={
    "SFDC Email Quotation Raw":(
        "SFDC Quotation ID","Active","Opportunity ID",
        "Total Price USD (converted) Currency","Total Price USD (converted)"),
    "Quote Approval Dedup":("Approval KST","Quotation Name","SFDC Record ID"),
    "Quote Portfolio":("Salesforce Quote ID (18)","Quote QID","Quote USD"),
    "SFDC Email Ingest Audit":("Entity","Source Received KST","State"),
}
QID_RE=re.compile(r"(?<![A-Za-z0-9-])(QID-\d{4}-\d{2}-\d{2}-[A-Za-z0-9]+)(?![A-Za-z0-9-])",re.I)
ID_RE=re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?")
RANGES={
    "SFDC Email Quotation Raw":"A1:Y4500",
    "Quote Approval Dedup":"A1:Q1600",
    "Quote Portfolio":"A1:I2800",
    "SFDC Email Ingest Audit":"A1:J15",
}

def read_sources():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    credential=os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not credential:raise RuntimeError("READONLY_SHEETS_CREDENTIAL_MISSING")
    auth=service_account.Credentials.from_service_account_info(
        json.loads(credential),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    client=AuthorizedSession(auth)
    output={}
    for tab,rng in RANGES.items():
        a1=urllib.parse.quote("'"+tab.replace("'","''")+"'!"+rng,safe="")
        result=client.get("https://sheets.googleapis.com/v4/spreadsheets/"+
                          BOOK+"/values/"+a1,timeout=55)
        if not result.ok:
            raise RuntimeError("QUOTE_BRIDGE_SOURCE_GET_FAILED_"+str(result.status_code))
        output[tab]=result.json().get("values",[])
    return output

def rows(matrix,required):
    if not matrix or not set(required).issubset(matrix[0]):
        raise ValueError("QUOTE_BRIDGE_SCHEMA_MISMATCH")
    columns=matrix[0]
    return [{name:str(row[i]).strip() if i<len(row) and row[i] is not None else ""
             for i,name in enumerate(columns)}
            for row in matrix[1:] if any(str(v or "").strip() for v in row)]

def money(value):
    x=str(value or "").strip().replace(",","")
    if not re.fullmatch(r"\d+(?:\.\d+)?",x):
        return None
    try:return Decimal(x)
    except InvalidOperation:return None

def single_qid(s):
    found={m.group(1).upper() for m in QID_RE.finditer(str(s or ""))}
    return next(iter(found)) if len(found)==1 else None

def strict_active(s):
    return {"1":True,"0":False,"true":True,"false":False,
            "yes":True,"no":False}.get(str(s).strip().lower())

def sf15(s):
    value=str(s or "").strip()
    return value[:15] if ID_RE.fullmatch(value) else None

def friday(day):
    return day-dt.timedelta(days=(day.weekday()-4)%7)

def last_four(today):
    current=friday(today)
    return {(current-dt.timedelta(days=7*i)).isoformat() for i in range(1,5)}

def get_freshness(audit,now):
    found=[r for r in audit if r["Entity"]=="Quotation"]
    if len(found)!=1:return False,None
    record=found[0]
    try:
        stamp=dt.datetime.strptime(record["Source Received KST"].replace(" KST",""),
                                  "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except ValueError:return False,None
    age=(now-stamp).total_seconds()/3600
    return bool(0<=age<=48 and record["State"] in (
        "STAGED_NOT_PROMOTED","PRESERVED_NO_NEW_REPORT")),round(age,2)

def quote_index(raw):
    grouped=collections.defaultdict(list)
    invalid_key=0
    for row in raw:
        qid=str(row["SFDC Quotation ID"]).strip().upper()
        if not QID_RE.fullmatch(qid):
            invalid_key+=1
            continue
        grouped[qid].append(row)
    valid={}
    conflict=collections.Counter()
    for qid,entries in grouped.items():
        act={strict_active(r["Active"]) for r in entries}
        val={money(r["Total Price USD (converted)"]) for r in entries}
        currency={r["Total Price USD (converted) Currency"].strip().upper()
                  for r in entries}
        opportunity={r["Opportunity ID"].strip() for r in entries}
        if len(act)!=1 or None in act:conflict["active"]+=1;continue
        if len(val)!=1 or None in val:conflict["amount"]+=1;continue
        if currency!={"USD"}:conflict["currency"]+=1;continue
        if len(opportunity)!=1 or "" in opportunity:conflict["opportunity"]+=1;continue
        valid[qid]={"active":next(iter(act)), "amount":next(iter(val)),
                    "opportunity":next(iter(opportunity)),"rows":len(entries)}
    return valid,{"unique_qids":len(grouped),"valid_qids":len(valid),
                  "invalid_key_rows":invalid_key,
                  "inconsistent_qids":len(grouped)-len(valid),
                  "issues":dict(conflict)}

def portfolio_index(data):
    output=collections.defaultdict(list)
    for row in data:
        qid=str(row["Quote QID"]).strip().upper()
        sf=sf15(row["Salesforce Quote ID (18)"])
        if qid and sf:output[qid].append((sf,money(row["Quote USD"])))
    return output

def analyze(data,now=None):
    now=now or dt.datetime.now(KST)
    if now.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    src={tab:rows(data[tab],REQUIRED[tab]) for tab in REQUIRED}
    fresh,age=get_freshness(src["SFDC Email Ingest Audit"],now)
    qidx,qstatus=quote_index(src["SFDC Email Quotation Raw"])
    historic=portfolio_index(src["Quote Portfolio"])
    four=last_four(now.date())
    statistics=collections.defaultdict(lambda:collections.Counter())
    amount_totals=collections.defaultdict(lambda:Decimal(0))
    seen=collections.defaultdict(set)
    global_ids=collections.defaultdict(set)
    parity={"old_value_compared":0,"old_value_equal":0,"old_value_conflicts":0}
    matched_historic=set()
    for entry in src["Quote Approval Dedup"]:
        date_s=entry["Approval KST"][:10]
        try:day=dt.date.fromisoformat(date_s)
        except ValueError:continue
        week=friday(day).isoformat()
        if week not in four:continue
        stat=statistics[week]
        stat["approval_evidence_rows"]+=1
        qid=single_qid(entry["Quotation Name"])
        if qid is None:
            stat["no_unique_qid_in_name"]+=1
            continue
        stat["qid_extracted"]+=1
        sf=sf15(entry["SFDC Record ID"])
        if not sf:stat["missing_immutable_sf_id"]+=1;continue
        global_ids[qid].add(sf)
        if qid in seen[week]:
            stat["duplicate_qid_evidence"]+=1
            continue
        seen[week].add(qid)
        candidate=qidx.get(qid)
        if candidate is None:
            stat["qid_missing_or_inconsistent_in_3report"]+=1
            continue
        stat["qid_exact_report_match"]+=1
        if not candidate["active"]:
            stat["report_inactive"]+=1
            continue
        stat["report_active"]+=1
        old=historic.get(qid,[])
        old_distinct={(rid,price) for rid,price in old}
        # A historic QID crosswalk is independent evidence tying QID to SF record ID.
        historic_id=bool(old_distinct) and {rid for rid,_ in old_distinct}=={sf}
        if historic_id:
            stat["historic_record_id_confirmed"]+=1
            if qid not in matched_historic:
                for rid,price in old_distinct:
                    if price is not None:
                        parity["old_value_compared"]+=1
                        if abs(price-candidate["amount"])<=Decimal("0.01"):
                            parity["old_value_equal"]+=1
                        else:parity["old_value_conflicts"]+=1
                matched_historic.add(qid)
        else:
            stat["qid_only_no_historic_sf_crosswalk"]+=1
        if fresh and historic_id:
            stat["fresh_active_record_id_verified"]+=1
            amount_totals[week]+=candidate["amount"]
        elif fresh:
            stat["fresh_active_qid_candidate_only"]+=1
    for qid,identities in global_ids.items():
        if len(identities)>1:
            for week in statistics:
                statistics[week]["qid_to_sf_id_conflicts"]+=1
    week_rows=[]
    for week in sorted(four):
        row={"week_start":week,**statistics[week]}
        row["verified_crosswalk_k_usd"]=str((amount_totals[week]/1000).quantize(Decimal("0.0001")))
        week_rows.append(row)
    block=[]
    if not fresh:block.append("3REPORT_QUOTATION_SNAPSHOT_STALE")
    if qstatus["inconsistent_qids"]:block.append("QUOTE_PRODUCT_ROW_INCONSISTENCIES")
    if parity["old_value_conflicts"]:block.append("HISTORIC_PRICE_PARITY_MISMATCH")
    if any((r.get("qid_only_no_historic_sf_crosswalk",0)+
            r.get("qid_missing_or_inconsistent_in_3report",0)+
            r.get("no_unique_qid_in_name",0)+r.get("report_inactive",0)) for r in week_rows):
        block.append("SOME_APPROVALS_NOT_FULLY_RECONCILED")
    block.append("SALES_OWNER_SCOPE_NOT_VERIFIED")
    return {"status":"HOLD" if block else "PASS",
            "source_age_hours":age,"fresh":fresh,"product_rows":len(src["SFDC Email Quotation Raw"]),
            "quote_index":qstatus,"historic_overlap":parity,"four_weeks":week_rows,
            "blockers":block,
            "note":"A crosswalk amount is quote-level once only. Counts are not owner-verified; do not promote to revenue."}

def markdown(r):
    output=["## SFDC Quotation 3-report alternative amount bridge (read-only)",
      "", "**Status: "+r["status"]+"**; 3-report age "+
      str(r["source_age_hours"])+" hours; product rows "+
      str(r["product_rows"])+"; unique QIDs "+
      str(r["quote_index"]["unique_qids"])+".", "",
      "| Week | Approval evidence | QID extracted | Exact QID match | Active | SF ID crosswalk | QID-only | Crosswalk K USD |",
      "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in r["four_weeks"]:
        output.append("| "+x["week_start"]+" | "+
           str(x.get("approval_evidence_rows",0))+" | "+
           str(x.get("qid_extracted",0))+" | "+
           str(x.get("qid_exact_report_match",0))+" | "+
           str(x.get("report_active",0))+" | "+
           str(x.get("historic_record_id_confirmed",0))+" | "+
           str(x.get("qid_only_no_historic_sf_crosswalk",0))+" | "+
           x["verified_crosswalk_k_usd"]+" |")
    output+=["","Historic amount cross-check: "+json.dumps(r["historic_overlap"],sort_keys=True),
       "Product-row QID consistency: "+json.dumps(r["quote_index"],sort_keys=True),
       "Blockers: "+", ".join(r["blockers"]), "",
       "No customer data, quote IDs, opportunity IDs or product rows are exposed. "
       "Candidate USD amounts are NOT monthly Revenue or finalized owner-scoped Quote KPIs."]
    return "\n".join(output)

def main():
    report=analyze(read_sources())
    print(markdown(report))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as fh:
            fh.write(markdown(report)+"\n")
    print("SFDC_3REPORT_QUOTE_BRIDGE="+report["status"])
    return 2 if report["status"]=="HOLD" else 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as e:
        print("SFDC_3REPORT_QUOTE_BRIDGE_ERROR="+type(e).__name__,file=sys.stderr)
        sys.exit(1)
