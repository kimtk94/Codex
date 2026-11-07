#!/usr/bin/env python3
"""Reconcile current SFDC three-report Quote PROCESS charges, without unsafe FX.

The Email Quotation report contains one row per process, not per Quotation.
The only monetary candidate is SUM(Unit Price USD * Sample Quantity) for all
distinct priced process lines in one QID. Zero-price lines are legitimate.
A duplicate exact priced process, mismatched historical quote, unverified owner,
stale snapshot, or missing source evidence is excluded. Not invoiced Revenue.
"""
import collections
import datetime as dt
import decimal
import hashlib
import json
import re
from zoneinfo import ZoneInfo

D=decimal.Decimal
KST=ZoneInfo("Asia/Seoul")
QID=re.compile(r"QID-\d{4}-\d{2}-\d{2}-[A-Za-z0-9]+",re.I)
SFID=re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?")
APPROVED_SOURCE_STATES={"STAGED_NOT_PROMOTED","PRESERVED_NO_NEW_REPORT"}
MY_SALES_OWNER="Kim Taehoon"

def cell(row,key):
    return str(row.get(key) or "").strip()

def amount(text):
    value=str(text or "").replace(",","").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?",value):
        return None
    try:
        number=D(value)
        return number if number.is_finite() else None
    except decimal.InvalidOperation:
        return None

def quote_id(text):
    found={m.group().upper() for m in QID.finditer(str(text or ""))}
    return next(iter(found)) if len(found)==1 else None

def sf15(text):
    text=str(text or "").strip()
    return text[:15] if SFID.fullmatch(text) else None

def week_for(date_text):
    try:
        date=dt.date.fromisoformat(str(date_text)[:10])
    except ValueError:
        return None
    return (date-dt.timedelta(days=(date.weekday()-4)%7)).isoformat()

def source_fresh(stamp,now,max_hours=48):
    try:
        when=dt.datetime.strptime(str(stamp or "").replace(" KST","").strip(),
                                  "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except ValueError:
        return False
    age=(now-when).total_seconds()
    return 0<=age<=max_hours*3600

def exact_source_sha(rows):
    """Reproduce the SFDC 3-report importer digest, retaining all trailing blanks."""
    if not rows:
        return None
    keys=list(rows[0])
    matrix=[[cell(item,key) for key in keys] for item in rows]
    return hashlib.sha256(json.dumps([keys,matrix],ensure_ascii=False,
                     separators=(",",":")).encode("utf-8")).hexdigest()

def validate_source(source,now):
    """Fail closed against the authenticated QQ report ingest manifest."""
    reports=(("Quotation","SFDC Email Quotation Raw","SFDC Quotation ID"),
             ("Opportunities","SFDC Email Opportunities Raw","Opportunity ID"))
    audit=source.get("SFDC Email Ingest Audit",[])
    for entity,tab,key in reports:
        rows=source.get(tab,[])
        records=[r for r in audit if cell(r,"Entity")==entity]
        if len(records)!=1 or not rows:
            return "WITHHELD_3REPORT_SOURCE_MISSING"
        record=records[0]
        if cell(record,"State") not in APPROVED_SOURCE_STATES:
            return "WITHHELD_3REPORT_INGEST_STATUS"
        if cell(record,"Source Kind")!="QQ IMAP":
            return "WITHHELD_3REPORT_UNTRUSTED_ORIGIN"
        if not source_fresh(cell(record,"Source Received KST"),now):
            return "WITHHELD_3REPORT_STALE"
        counted=amount(cell(record,"Rows"))
        unique=amount(cell(record,"Unique IDs"))
        ids=[cell(row,key) for row in rows]
        if any(not v for v in ids) or counted!=len(rows) or unique!=len(set(ids)):
            return "WITHHELD_3REPORT_COVERAGE_MISMATCH"
        digest=cell(record,"Content SHA256")
        if not re.fullmatch(r"[a-fA-F0-9]{64}",digest):
            return "WITHHELD_3REPORT_SHA_MISSING"
        if exact_source_sha(rows).lower()!=digest.lower():
            return "WITHHELD_3REPORT_SHA_MISMATCH"
    return "SOURCE_QQ_REPORT_VERIFIED"

def process_totals(rows):
    """Build QID quotes, never summing quote-level converted totals.

    An exact duplicate priced process is a HOLD; a repeated process name with
    different pricing/quantity is valid and charged independently.
    """
    by_qid=collections.defaultdict(lambda:{"opportunities":set(),"active":set(),
                                             "ids":set(),"sum":D(0),"positive":0,
                                             "bad":set()})
    for row in rows:
        qid=cell(row,"SFDC Quotation ID").upper()
        state=by_qid[qid]
        if not QID.fullmatch(qid):
            state["bad"].add("MALFORMED_QID")
        state["opportunities"].add(cell(row,"Opportunity ID"))
        state["active"].add(cell(row,"Active").lower())
        price=amount(cell(row,"Unit Price USD"))
        qty=amount(cell(row,"Sample Quantity"))
        if price is None or qty is None or price<0 or qty<=0:
            state["bad"].add("INVALID_PROCESS_PRICE_OR_QTY")
            continue
        if price==0:
            continue
        product=cell(row,"Quotation Product ID")
        process=cell(row,"Process Name: SFDC Process ID")
        if not product or not process:
            state["bad"].add("MISSING_CHARGED_PROCESS_ID")
            continue
        identity=(product,process,price,qty)
        if identity in state["ids"]:
            state["bad"].add("EXACT_DUPLICATE_CHARGE")
            continue
        state["ids"].add(identity)
        state["sum"]+=price*qty
        state["positive"]+=1
    accepted={}
    reasons=collections.Counter()
    for qid,entry in by_qid.items():
        if len(entry["opportunities"])!=1 or "" in entry["opportunities"]:
            entry["bad"].add("AMBIGUOUS_OPPORTUNITY")
        if entry["active"]!={"1"}:
            entry["bad"].add("NOT_UNIQUELY_ACTIVE")
        if not entry["positive"]:
            entry["bad"].add("NO_POSITIVE_PROCESS_PRICE")
        if entry["bad"]:
            reasons.update(entry["bad"])
            continue
        accepted[qid]={"opportunity":next(iter(entry["opportunities"])),
                       "amount_usd":entry["sum"]}
    return accepted,{"unique_quote_ids":len(by_qid),
                     "candidate_quote_ids":len(accepted),
                     "held_quote_ids":len(by_qid)-len(accepted),
                     "hold_reasons":dict(reasons)}

def owner_lookup(rows):
    mapping=collections.defaultdict(set)
    for row in rows:
        oid=cell(row,"Opportunity ID")
        if oid:
            mapping[oid].add(cell(row,"Opportunity Owner"))
    return mapping

def historic_quote_map(rows):
    result=collections.defaultdict(list)
    for row in rows:
        qid=cell(row,"Quote QID").upper()
        if qid:
            result[qid].append((sf15(cell(row,"Salesforce Quote ID (18)")),
                                amount(cell(row,"Quote USD"))))
    return result

def prepare(source,now):
    guard=validate_source(source,now)
    if guard!="SOURCE_QQ_REPORT_VERIFIED":
        return {},{"source_state":guard}
    result,stats=process_totals(source["SFDC Email Quotation Raw"])
    return result,{"source_state":guard,**stats}

def weekly_calculations(source,now):
    """Return week-level *calculated estimate* and exceptions, not booked revenue."""
    candidates,source_info=prepare(source,now)
    owners=owner_lookup(source.get("SFDC Email Opportunities Raw",[]))
    history=historic_quote_map(source.get("Quote Portfolio",[]))
    approvals=collections.defaultdict(dict)
    issues=collections.defaultdict(collections.Counter)
    for row in source.get("Quote Approval Dedup",[]):
        week=week_for(cell(row,"Approval KST"))
        if not week:
            continue
        sid=sf15(cell(row,"SFDC Record ID"))
        qid=quote_id(cell(row,"Quotation Name"))
        if not sid or not qid:
            issues[week]["invalid_approval_identifier"]+=1
            continue
        prior=approvals[week].get(sid)
        if prior and prior!=qid:
            issues[week]["conflicting_sf_id_qid"]+=1
            approvals[week][sid]=None
        else:
            approvals[week][sid]=qid
    results={}
    for wk,seen in approvals.items():
        result={"source_state":source_info["source_state"],
                "approval_ids":len(seen),"calculated_count":0,
                "created_in_week_count":sum(
                    1 for qid in seen.values() if qid and
                    week_for(qid[4:14])==wk),
                "candidate_usd":D(0),"issues":collections.Counter(issues[wk]),
                "hist_parity_count":0,"without_historic_count":0}
        if source_info["source_state"]!="SOURCE_QQ_REPORT_VERIFIED":
            results[wk]=result
            continue
        qids=list(seen.values())
        if None in qids or len(set(qids))!=len(qids):
            result["issues"]["qid_sf_crosswalk_ambiguous"]+=1
            results[wk]=result
            continue
        for sid,qid in seen.items():
            quote=candidates.get(qid)
            if not quote:
                result["issues"]["no_safe_priced_quote"]+=1
                continue
            quote_owners=owners.get(quote["opportunity"],set())
            if quote_owners!={MY_SALES_OWNER}:
                result["issues"]["opportunity_owner_unverified_or_other"]+=1
                continue
            past=history.get(qid,[])
            if past:
                distinct=set(past)
                if len(distinct)!=1:
                    result["issues"]["historic_quote_conflict"]+=1
                    continue
                old_sf,old_price=next(iter(distinct))
                if old_sf!=sid or old_price is None or old_price<0:
                    result["issues"]["historic_immutable_id_or_price_mismatch"]+=1
                    continue
                new=quote["amount_usd"]
                if abs(old_price-new)>max(D("1"),new*D("0.02")):
                    result["issues"]["historic_amount_disagrees"]+=1
                    continue
                result["hist_parity_count"]+=1
            else:
                result["without_historic_count"]+=1
            result["calculated_count"]+=1
            result["candidate_usd"]+=quote["amount_usd"]
        results[wk]=result
    return results,source_info
