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
        "Total Price USD (converted) Currency","Total Price USD (converted)",
        "Quotation Product ID","Process Name: SFDC Process ID",
        "Unit Price USD","Sample Quantity"),
    "Quote Approval Dedup":("Approval KST","Quotation Name","SFDC Record ID"),
    "Quote Portfolio":("Salesforce Quote ID (18)","Quote QID","Quote USD"),
    "SFDC Email Ingest Audit":("Entity","Source Received KST","State"),
    "SFDC Email Opportunities Raw":("Opportunity ID","Opportunity Owner","Amount Currency"),
    "SFDC Import Opportunities":("Opportunity ID","Opportunity Owner"),
}
QID_RE=re.compile(r"(?<![A-Za-z0-9-])(QID-\d{4}-\d{2}-\d{2}-[A-Za-z0-9]+)(?![A-Za-z0-9-])",re.I)
ID_RE=re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?")
RANGES={
    "SFDC Email Quotation Raw":"A1:Y4500",
    "Quote Approval Dedup":"A1:Q1600",
    "Quote Portfolio":"A1:I2800",
    "SFDC Email Ingest Audit":"A1:J15",
    "SFDC Email Opportunities Raw":"A1:O900",
    "SFDC Import Opportunities":"A1:O900",
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

def source_owner_map(opportunities):
    by_id=collections.defaultdict(set)
    for row in opportunities:
        opportunity=row["Opportunity ID"].strip()
        if opportunity:
            by_id[opportunity].add(row["Opportunity Owner"].strip())
    return {opportunity:next(iter(owners)) if len(owners)==1 else None
            for opportunity,owners in by_id.items()}

def portfolio_unit_check(qidx,portfolio):
    buckets={"compared":0,"direct_usd_parity":0,"ratio_near_1500":0,"other_ratio":0,"not_comparable":0}
    old=portfolio_index(portfolio)
    for qid,entries in old.items():
        source=qidx.get(qid)
        distinct={(sf,price) for sf,price in entries}
        if not source or len(distinct)!=1:
            buckets["not_comparable"]+=1
            continue
        amount=source["amount"]
        old_amount=next(iter(distinct))[1]
        if old_amount is None or amount<=0:
            buckets["not_comparable"]+=1
            continue
        buckets["compared"]+=1
        if abs(old_amount-amount)<=max(Decimal("0.01"),abs(amount)*Decimal("0.001")):
            buckets["direct_usd_parity"]+=1
        elif abs(old_amount/amount-Decimal(1500))<=Decimal(75):
            buckets["ratio_near_1500"]+=1
        else:
            buckets["other_ratio"]+=1
    return buckets

def safe_process_amount_sums(process_rows):
    """Independent QID-level USD candidates from distinct positive process lines.

    The Quote process report can contain multiple chargeable processes per
    product. Never choose one price per product. Repeated positive
    (Quotation Product ID, SFDC Process ID, Unit Price, Quantity) keys fail closed.
    Discounts, credits, and line-item completeness still need source QC.
    """
    entries=collections.defaultdict(lambda:{"sum":Decimal(0),"keys":set(),
                                       "invalid":False,"positive":0})
    all_ids=set()
    duplicate_process_keys=missing_process_identity=0
    for row in process_rows:
        qid=row["SFDC Quotation ID"].strip().upper()
        if not qid:continue
        all_ids.add(qid)
        price=money(row["Unit Price USD"])
        quantity=money(row["Sample Quantity"])
        if price is None or quantity is None or price<=0 or quantity<=0:
            continue
        item=entries[qid]
        item["positive"]+=1
        product=row["Quotation Product ID"].strip()
        process=row["Process Name: SFDC Process ID"].strip()
        if not product or not process:
            missing_process_identity+=1
            item["invalid"]=True
            continue
        # SFDC process identifiers can recur within one quotation product
        # for distinct priced/quantity lines. Block only exact charge-row
        # repeats; normalize numeric values before comparing identities.
        key=(product,process,price,quantity)
        if key in item["keys"]:
            duplicate_process_keys+=1
            item["invalid"]=True
            continue
        item["keys"].add(key)
        item["sum"]+=price*quantity
    valid={qid:item["sum"] for qid,item in entries.items()
           if not item["invalid"] and item["sum"]>0}
    blocked=sum(item["invalid"] for item in entries.values())
    return valid,{"quote_qids":len(all_ids),"positive_process_rows":sum(
                     item["positive"] for item in entries.values()),
                  "distinct_qids_with_positive_processes":len(entries),
                  "candidate_qids":len(valid),
                  "invalid_qids":blocked,
                  "duplicate_positive_process_keys":duplicate_process_keys,
                  "missing_positive_process_identity":missing_process_identity,
                  "no_positive_process_qids":len(all_ids)-len(entries)}

def currency_and_price_evidence(process_rows,qidx,portfolio,opportunities):
    """Count conversion behaviors by original Opportunity currency.

    Historic Quote USD is numeric evidence, *not* a proven unit. Never
    interpret an observed 1500x ratio as permission for financial conversion.
    """
    by_opp=collections.defaultdict(set)
    for row in opportunities:
        if row["Opportunity ID"].strip():
            by_opp[row["Opportunity ID"].strip()].add(row["Amount Currency"].strip().upper())
    price_units,process_diag=safe_process_amount_sums(process_rows)
    hist=portfolio_index(portfolio)
    output={name:{"compared":0,"ratio_near_1":0,"ratio_near_1500":0,
                  "other_ratio":0,"price_unit_sum_present":0,
                  "historic_close_to_process_sum_2pct":0,
                  "historic_close_to_process_sum_10pct":0} for name in ("KRW","USD","UNKNOWN")}
    noncomparable=0
    for qid,old_entries in hist.items():
        source=qidx.get(qid)
        distinct=set(old_entries)
        if not source or len(distinct)!=1:
            noncomparable+=1
            continue
        old_price=next(iter(distinct))[1]
        report_price=source["amount"]
        if old_price is None or report_price<=0:
            noncomparable+=1
            continue
        currencies=by_opp.get(source["opportunity"],set())
        curr=next(iter(currencies)) if len(currencies)==1 else "UNKNOWN"
        if curr not in ("KRW","USD"):curr="UNKNOWN"
        item=output[curr]
        item["compared"]+=1
        rate=old_price/report_price
        if abs(rate-1)<=Decimal("0.02"):
            item["ratio_near_1"]+=1
        elif abs(rate-1500)<=Decimal(75):
            item["ratio_near_1500"]+=1
        else:
            item["other_ratio"]+=1
        unit_sum=price_units.get(qid)
        if unit_sum is not None:
            item["price_unit_sum_present"]+=1
            if abs(old_price-unit_sum)<=max(Decimal("0.01"),unit_sum*Decimal("0.02")):
                item["historic_close_to_process_sum_2pct"]+=1
            if abs(old_price-unit_sum)<=max(Decimal("1"),unit_sum*Decimal("0.10")):
                item["historic_close_to_process_sum_10pct"]+=1
    return {"by_opportunity_currency":output,"not_comparable":noncomparable,
            "process_evidence":process_diag,
            "assurance":"READ_ONLY_PROCESS_SUM_CANDIDATE_NOT_FINAL_QUOTE_PRICE"}

def analyze(data,now=None):
    now=now or dt.datetime.now(KST)
    if now.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    src={tab:rows(data[tab],REQUIRED[tab]) for tab in REQUIRED}
    fresh,age=get_freshness(src["SFDC Email Ingest Audit"],now)
    qidx,qstatus=quote_index(src["SFDC Email Quotation Raw"])
    historic=portfolio_index(src["Quote Portfolio"])
    owner_by_opp=source_owner_map(src["SFDC Email Opportunities Raw"])
    older_owner_by_opp=source_owner_map(src["SFDC Import Opportunities"])
    unit_check=portfolio_unit_check(qidx,src["Quote Portfolio"])
    process_sums,process_status=safe_process_amount_sums(src["SFDC Email Quotation Raw"])
    currency_evidence=currency_and_price_evidence(src["SFDC Email Quotation Raw"],qidx,
        src["Quote Portfolio"],src["SFDC Email Opportunities Raw"])
    four=last_four(now.date())
    statistics=collections.defaultdict(lambda:collections.Counter())
    # Withhold all monetary sums until the USD-vs-FX unit discrepancy is resolved.
    seen=collections.defaultdict(set)
    global_ids=collections.defaultdict(set)
    absent_opportunity_ids=set()
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
        process_sum=process_sums.get(qid)
        if process_sum is not None:
            stat["positive_process_amount_candidate"]+=1
        else:
            stat["process_amount_missing_or_ambiguous"]+=1
        owner=owner_by_opp.get(candidate["opportunity"])
        if owner is None or not owner:
            stat["owner_unresolved"]+=1
            if candidate["opportunity"] not in older_owner_by_opp:
                stat["owner_opp_missing_in_both_reports"]+=1
                absent_opportunity_ids.add(candidate["opportunity"])
            else:
                stat["owner_opp_found_in_older_report_only"]+=1
        elif owner=="Kim Taehoon":
            stat["my_owner_verified"]+=1
        else:
            stat["other_sales_owner_verified"]+=1
        old=historic.get(qid,[])
        old_distinct={(rid,price) for rid,price in old}
        # A historic QID crosswalk is independent evidence tying QID to SF record ID.
        historic_id=bool(old_distinct) and {rid for rid,_ in old_distinct}=={sf}
        if historic_id:
            stat["historic_record_id_confirmed"]+=1
            if process_sum is not None and len(old_distinct)==1:
                historic_price=next(iter(old_distinct))[1]
                if historic_price is not None and abs(historic_price-process_sum)<=max(
                    Decimal("0.01"),process_sum*Decimal("0.02")):
                    stat["historic_process_amount_parity_2pct"]+=1
                else:
                    stat["historic_process_amount_mismatch"]+=1
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
        if process_sum is not None and owner=="Kim Taehoon":
            stat["my_owner_with_process_candidate"]+=1
        if fresh and historic_id:
            stat["fresh_active_record_id_crosswalk"]+=1
        elif fresh:
            stat["fresh_active_qid_candidate_only"]+=1
    for qid,identities in global_ids.items():
        if len(identities)>1:
            for week in statistics:
                if qid in seen[week]:
                    statistics[week]["qid_to_sf_id_conflicts"]+=1
    week_rows=[]
    for week in sorted(four):
        row={"week_start":week,**statistics[week]}
        row["amount_display"]="WITHHELD_UNIT_PARITY"
        week_rows.append(row)
    block=[]
    if not fresh:block.append("3REPORT_QUOTATION_SNAPSHOT_STALE")
    if qstatus["inconsistent_qids"]:block.append("QUOTE_PRODUCT_ROW_INCONSISTENCIES")
    if parity["old_value_conflicts"]:block.append("HISTORIC_PRICE_PARITY_MISMATCH")
    if any((r.get("qid_only_no_historic_sf_crosswalk",0)+
            r.get("qid_missing_or_inconsistent_in_3report",0)+
            r.get("no_unique_qid_in_name",0)+r.get("report_inactive",0)) for r in week_rows):
        block.append("SOME_APPROVALS_NOT_FULLY_RECONCILED")
    if any(r.get("owner_unresolved",0)+r.get("other_sales_owner_verified",0) for r in week_rows):
        block.append("OWNER_SCOPE_REVIEW_REQUIRED")
    if unit_check["ratio_near_1500"] or unit_check["other_ratio"]:
        block.append("SOURCE_AMOUNT_UNIT_CONFLICT")
    return {"status":"HOLD" if block else "PASS",
            "source_age_hours":age,"fresh":fresh,"product_rows":len(src["SFDC Email Quotation Raw"]),
            "quote_index":qstatus,"historic_overlap":parity,
            "portfolio_unit_check":unit_check,
            "process_amount_evidence":process_status,
            "missing_distinct_opportunity_ids":len(absent_opportunity_ids),
            "currency_and_unit_evidence":currency_evidence,"four_weeks":week_rows,
            "blockers":block,
            "note":"A crosswalk amount is quote-level once only. Counts are not owner-verified; do not promote to revenue."}

def markdown(r):
    output=["## SFDC Quotation 3-report alternative amount bridge (read-only)",
      "", "**Status: "+r["status"]+"**; 3-report age "+
      str(r["source_age_hours"])+" hours; product rows "+
      str(r["product_rows"])+"; unique QIDs "+
      str(r["quote_index"]["unique_qids"])+".", "",
      "| Week | Approval evidence | QID matched | Active | My owner | Owner unknown | Process amount candidates | Historic process parity | Amount |",
      "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for x in r["four_weeks"]:
        output.append("| "+x["week_start"]+" | "+
           str(x.get("approval_evidence_rows",0))+" | "+
           str(x.get("qid_exact_report_match",0))+" | "+
           str(x.get("report_active",0))+" | "+
           str(x.get("my_owner_verified",0))+" | "+
           str(x.get("owner_unresolved",0))+" | "+
           str(x.get("positive_process_amount_candidate",0))+" | "+
           str(x.get("historic_process_amount_parity_2pct",0))+" | "+
           x["amount_display"]+" |")
    output+=["","Historic amount cross-check: "+json.dumps(r["historic_overlap"],sort_keys=True),
       "Product-row QID consistency: "+json.dumps(r["quote_index"],sort_keys=True),
       "Process line amount provenance: "+json.dumps(r["process_amount_evidence"],sort_keys=True),
       "Portfolio price unit check: "+json.dumps(r["portfolio_unit_check"],sort_keys=True),
       "Currency and independent unit-price check: "+json.dumps(
           r["currency_and_unit_evidence"],sort_keys=True),
       "Owner IDs absent from both fresh and older Opportunity sources: "+
       str(sum(x.get("owner_opp_missing_in_both_reports",0) for x in r["four_weeks"])),
       "Distinct missing Opportunity IDs: "+str(r["missing_distinct_opportunity_ids"]),
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
