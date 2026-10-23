#!/usr/bin/env python3
"""Quote Active/amount reconciliation with strict Salesforce-export provenance.

Only Salesforce Quote object exports with stable identifiers and explicit Active
may promote approved quotes. Opportunity-stage values never substitute for IsActive.
"""
import datetime as dt
import re
from collections import defaultdict
import incremental_sync as css
from unified_followup_sync import DST, KST, get, put, ensure, base

REQUIRED={
    "salesforce record id":("salesforce record id","sfdc quotation id","quote id","quotation record id"),
    "active":("isactive","is active","active"),
    "amount":("total amount","grand total","quotation total","quote amount"),
    "currency":("currency","currencyisocode","quote currency"),
    "opportunity id":("opportunity id","related opportunity id")
}
def norm(v):return " ".join(str(v or "").strip().casefold().replace("_"," ").split())
def indices(headers):
    names={norm(v):i for i,v in enumerate(headers)}
    out={}
    for key,options in REQUIRED.items():
        matched=[names[k] for k in options if k in names]
        if len(set(matched))==1:out[key]=matched[0]
    return out
def missing(headers):
    valid=indices(headers)
    return [k for k in REQUIRED if k not in valid]
def active(v):
    value=str(v).strip().lower()
    return True if value in ("true","yes","1","active") else False if value in ("false","no","0","inactive") else None
def amount(v):
    cleaned=re.sub("[,₩$ ]","",str(v or ""))
    if not re.fullmatch(r"-?\d+(?:\.\d+)?",cleaned):return None
    val=float(cleaned)
    return val if val>=0 else None
def main():
    s=css.authorize()
    rows=get(s,DST,"Quotation","A1:Z1000")
    if not rows:raise RuntimeError("SFDC_QUOTATION_SOURCE_NOT_FOUND")
    absent=missing(rows[0]);ensure(s,DST,"Automation Health")
    timestamp=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    if absent:
        put(s,DST,"Automation Health","A3",[["SFDC Quote",timestamp,"BLOCKED_EXPORT_MISSING_FIELDS",", ".join(absent)]])
        print("SFDC_ACTIVE_VALIDATION_BLOCKED missing="+",".join(absent)+" rows="+str(len(rows)-1))
        return
    fields=indices(rows[0])
    by_id=defaultdict(list)
    for row in rows[1:]:
        row=row+[""]*max(0,len(rows[0])-len(row))
        rid=str(row[fields["salesforce record id"]]).strip()
        if re.fullmatch(r"a0P[A-Za-z0-9]{12,15}",rid):by_id[rid].append(row)
    approvals=get(s,DST,"Quote Approval Dedup","A1:K2000")
    if not approvals:raise RuntimeError("APPROVED_QUOTE_LIST_NOT_FOUND")
    output=[["Quote Status","Currency","Amount Native","Approved AND Active","Verified Amount KRW","Verified Amount kUSD"]]
    summary=defaultdict(lambda:{"count":0,"krw":0.0,"kusd":0.0})
    matched=0;ambiguous=0
    for r in approvals[1:]:
        rid=r[3] if len(r)>3 else ""
        matches=by_id.get(rid,[])
        values=["UNKNOWN","","","UNVERIFIED","",""]
        if len(matches)>1:ambiguous+=1
        elif len(matches)==1:
            hit=matches[0];is_active=active(hit[fields["active"]])
            val=amount(hit[fields["amount"]]);curr=str(hit[fields["currency"]]).strip().upper()
            valid=(is_active is not None and val is not None and curr in ("KRW","USD") and bool(str(hit[fields["opportunity id"]]).strip()))
            if valid:
                matched+=1
                values=["ACTIVE" if is_active else "INACTIVE",curr,val,"YES" if is_active else "NO",val if is_active and curr=="KRW" else "",round(val/1000,4) if is_active and curr=="USD" else ""]
                if is_active:
                    period=r[5] if len(r)>5 else ""
                    summary[period]["count"]+=1
                    summary[period]["krw"]+=val if curr=="KRW" else 0
                    summary[period]["kusd"]+=val/1000 if curr=="USD" else 0
        output.append(values)
    # Append to generated quote table only; original approval and source fields stay intact.
    meta=css.api(s,"GET",base(DST)+"?fields=sheets.properties(title,sheetId,gridProperties)")
    prop=next((x["properties"] for x in meta.get("sheets",[]) if x["properties"]["title"]=="Quote Approval Dedup"),None)
    if not prop:raise RuntimeError("QUOTE_TAB_MISSING")
    if prop.get("gridProperties",{}).get("columnCount",0)<17:
        css.api(s,"POST",base(DST)+":batchUpdate",json={"requests":[{"updateSheetProperties":{"properties":{"sheetId":prop["sheetId"],"gridProperties":{"columnCount":17}},"fields":"gridProperties.columnCount"}}]})
    put(s,DST,"Quote Approval Dedup","L1",output)
    weekly=get(s,DST,"SFDC Weekly Overview","A1:P1000")
    put(s,DST,"SFDC Weekly Overview","Q1",[["approved_active_kusd"]])
    for idx,r in enumerate(weekly[1:],2):
        if len(r)<2:continue
        period=str(r[0])+" ~ "+str(r[1])
        item=summary.get(period)
        if item:
            put(s,DST,"SFDC Weekly Overview","O"+str(idx),[[item["count"],round(item["krw"],2),round(item["kusd"],4)]])
    put(s,DST,"Automation Health","A3",[["SFDC Quote",timestamp,"VALIDATED_PARTIAL","matched="+str(matched)+" ambiguous="+str(ambiguous)+" source_rows="+str(len(rows)-1)]])
    print("SFDC_ACTIVE_VALIDATION_PASS matched="+str(matched)+" ambiguous="+str(ambiguous))
if __name__=="__main__":main()
