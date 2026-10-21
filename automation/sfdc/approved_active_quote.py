#!/usr/bin/env python3
"""Strict approved AND Salesforce-Active quote value reconciliation (no inference)."""
import re
import os
from collections import defaultdict
from datetime import datetime, timedelta

RATE=float(os.getenv("SFDC_KRW_PER_USD","1500"))

def col(headers,keys):
    h={str(x).strip().lower():i for i,x in enumerate(headers)}
    return next((h[k.lower()] for k in keys if k.lower() in h),None)

def cell(row,index):
    return str(row[index]).strip() if index is not None and len(row)>index and row[index] is not None else ""

def date(x):
    v=str(x or "")[:10]
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%y"):
        try:return datetime.strptime(v,fmt).date()
        except ValueError:pass
    return None

def fri_start(d):
    return d-timedelta(days=(d.weekday()-4)%7)

def amount(x):
    text=str(x).replace(",","").replace("₩","").replace("$","").strip()
    try:return float(text)
    except ValueError:return None

def active_value(x):
    v=str(x).strip().casefold()
    if v in ("true","yes","1","checked","✓","✔"):return True
    if v in ("false","no","0","unchecked"):return False
    return None

def weekly_verified(approvals,quotes):
    """Returns week => (count, total_krw, total_k_usd); unavailable if schema insufficient.
    Match only via immutable Salesforce quotation record ID or AMEA quotation ID.
    """
    if not approvals or not quotes:return {}, "MISSING_SOURCE"
    ah,qh=approvals[0],quotes[0]
    aid=col(ah,["salesforce_record_id"])
    aamea=col(ah,["quotation_id"])
    at=col(ah,["approved_at_kst"])
    qid=col(qh,["SFDC Quotation ID","Salesforce Quotation ID","Quote Record ID"])
    qamea=col(qh,["Quotation ID","AMEA No.","AMEA ID"])
    qactive=col(qh,["IsActive","Is Active","Active","Is Active Quote"])
    qamount=col(qh,["Grand Total","Quote Grand Total","Total Price","Quote Total","Total Amount"])
    qcurrency=col(qh,["Currency","Quotation Currency","Quote Currency","CurrencyIsoCode"])
    if at is None or (aid is None and aamea is None):return {}, "APPROVAL_KEYS_MISSING"
    if qactive is None or qamount is None or qcurrency is None or (qid is None and qamea is None):
        return {}, "QUOTE_ACTIVE_ID_AMOUNT_OR_CURRENCY_MISSING"
    byid=defaultdict(list)
    for quote in quotes[1:]:
        if qid is not None and cell(quote,qid):byid[("SFDC",cell(quote,qid))].append(quote)
        if qamea is not None and cell(quote,qamea):byid[("AMEA",cell(quote,qamea))].append(quote)
    perweek=defaultdict(dict)
    unresolved=0
    for a in approvals[1:]:
        day=date(cell(a,at))
        if day is None:continue
        keys=[]
        if aid is not None and cell(a,aid):keys.append(("SFDC",cell(a,aid)))
        if aamea is not None and cell(a,aamea):keys.append(("AMEA",cell(a,aamea)))
        matching=[]
        for key in keys:
            candidates=byid.get(key,[])
            if len(candidates)==1:
                matching=candidates
                break
        if len(matching)!=1:
            unresolved+=1
            continue
        quote=matching[0]
        if active_value(cell(quote,qactive)) is not True:continue
        price=amount(cell(quote,qamount))
        currency=cell(quote,qcurrency).upper()
        if price is None or currency not in ("KRW","USD"):
            unresolved+=1
            continue
        krw=price if currency=="KRW" else price*RATE
        usd_k=krw/RATE/1000
        quoteid=keys[0] if keys else ("ROW",str(quote))
        perweek[fri_start(day)][quoteid]=(krw,usd_k)
    # No amount can be declared complete when approval-to-quote matching is partial.
    if unresolved:return {}, f"INCOMPLETE_RELATIONSHIPS_{unresolved}"
    return {w:(len(records),round(sum(x[0] for x in records.values())),round(sum(x[1] for x in records.values()),3)) for w,records in perweek.items()},"VERIFIED"
