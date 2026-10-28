#!/usr/bin/env python3
"""Read-only statement=confirmation -> invoice billing-stage reconciliation.

Key is AMEA plus J/X/Z billing segment, never AMEA alone.
Personal owner: original official CSS notice directly addressed to Taehoon To/Cc.
Statement monetary value stays unverified unless backed by raw Statement body.
"""
import json,os,re,urllib.parse
import incremental_sync as src
MAIL_ID="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
BI_ID="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
PERSON="taehoon.kim@novogene.com"
AMEA=re.compile(r"AMEA\d{7,}(?:-\d{1,3})?",re.I)
SEG=re.compile(r"J\d+-X\d+SC\d+-Z\d+",re.I)
INVOICE=re.compile(r"Invoice Issued\s*&\s*Statement Confirmed",re.I)
STATEMENT=re.compile(r"Final Report\s*&\s*Statement Ready For Confirmation",re.I)
def get(session,book,tab,range_):
    url="https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+urllib.parse.quote("'"+tab+"'!"+range_,safe="")
    r=session.request("GET",url,timeout=120);r.raise_for_status()
    v=r.json().get("values",[])
    return [dict(zip(v[0],row)) for row in v[1:] if any(row)] if v else []
def identity(subject):
    a=AMEA.search(str(subject or ""));s=SEG.search(str(subject or ""))
    return (a.group().upper(),s.group().upper()) if a and s else None
def original(row):
    return (str(row.get("from_email","")).strip().lower()=="css@novogene-amea.com"
            and row.get("direction")=="INBOUND"
            and not str(row.get("in_reply_to","")).strip()
            and not re.match(r"^\s*(?:re|fw|fwd)\s*:",str(row.get("subject","")),re.I)
            and PERSON in (str(row.get("recipient_to",""))+" "+str(row.get("cc",""))).lower())
def main():
    session=src.authorize()
    mail=get(session,MAIL_ID,"CSS Git Ingest","A1:Q20000")
    legacy=get(session,MAIL_ID,"CSS Tax Invoice List","A1:N1500")
    quotes=get(session,BI_ID,"Quote Portfolio","A1:I1500")
    bill={}
    for row in mail:
        if not original(row):continue
        title=row.get("subject","")
        event="INVOICE" if INVOICE.search(title) else "STATEMENT" if STATEMENT.search(title) else None
        key=identity(title)
        if not event or not key:continue
        event_row={"uid":row.get("imap_uid",""),"received":row.get("received_at",""),
                   "subject":title,"key":key}
        state=bill.setdefault(key,{"invoice":[],"statement":[]})
        state["invoice" if event=="INVOICE" else "statement"].append(event_row)
    # Legacy ledger is used for matched issued amount, never to invent a pending amount.
    legacy_by_invoice={str(r.get("invoice_number","")).strip():r for r in legacy if r.get("invoice_number")}
    pending=[]
    issued=[]
    for key,state in bill.items():
        if state["invoice"]:
            issued.append(key)
            continue
        if not state["statement"]:continue
        # Limit quotation proxy to a unique ACTIVE quote for AMEA; do not call it Statement amount.
        q=[r for r in quotes if r.get("Active")=="ACTIVE" and
           (r.get("Approved AMEA ID")==key[0] or key[0] in str(r.get("Quote Name","")))]
        proxy=None
        if len(q)==1:
            try:proxy=float(q[0].get("Quote USD",""))
            except (ValueError,TypeError):pass
        newest=max(state["statement"],key=lambda r:r["received"])
        pending.append({"amea":key[0],"billing_segment":key[1],
           "statement_uid":newest["uid"],"statement_received":newest["received"],
           "statement_amount_krw":None,"amount_status":"STATEMENT_BODY_NOT_YET_VERIFIED",
           "quote_proxy_usd":proxy,"quote_proxy_not_revenue":True})
    pending.sort(key=lambda r:(r["statement_received"],r["amea"]))
    print("UNIFIED_STATEMENT_CONFIRMATION_LEDGER "+json.dumps({
       "personal_original_statement_events":sum(len(r["statement"]) for r in bill.values()),
       "personal_original_invoice_events":sum(len(r["invoice"]) for r in bill.values()),
       "billing_keys":len(bill),"issued_keys":len(issued),"pending_keys":len(pending),
       "pending_with_unique_active_quote":sum(r["quote_proxy_usd"] is not None for r in pending),
       "unverified_quote_proxy_total_usd":round(sum(r["quote_proxy_usd"] or 0 for r in pending),2),
       "statement_amount_verified":0,
       "pending":pending,"legacy_invoice_records":len(legacy_by_invoice),
       "revenue_mutated":False},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
