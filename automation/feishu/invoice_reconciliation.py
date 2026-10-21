"""Read-only, pure SFDC/CSS invoice vs Feishu payment reconciliation.

Input dictionaries are supplied by caller; never call APIs or send customer data to logs.
Review is mandatory for non-exact matches. No inferred paid status.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import re

def norm_id(v):
    return re.sub(r"[^A-Z0-9]","",str(v or "").upper())
def money(v):
    if v is None or str(v).strip()=="": return None
    try:
        s=str(v).strip().upper().replace(",", "").replace("₩", "").strip()
        if s.endswith("KRW"): s=s[:-3].strip()
        d=Decimal(s)
        if not d.is_finite():return None
        return d
    except InvalidOperation:return None

def reconcile(invoices, payments, quotations=()):
    """Returns private row-level candidates and aggregate counts; do not log rows."""
    inv_nums=[norm_id(i.get("invoice_number")) for i in invoices]
    if any(not k for k in inv_nums) or len(set(inv_nums))!=len(inv_nums):
        raise ValueError("Invoice identifiers missing or duplicated")
    pay_by_id={}
    for idx,p in enumerate(payments):
        key=norm_id(p.get("invoice_number"))
        if key:pay_by_id.setdefault(key,[]).append((idx,p))
    quotes={}
    for q in quotations:
        num=norm_id(q.get("invoice_number"))
        if num:quotes.setdefault(num,[]).append(q)
    results=[]
    for invoice,key in zip(invoices,inv_nums):
        candidates=pay_by_id.get(key,[])
        found=None
        status="REVIEW_NO_EXACT_MATCH"
        if len(candidates)>1:
            status="REVIEW_DUPLICATE_PAYMENT_ID"
        elif len(candidates)==1:
            idx,p=candidates[0]
            amount=money(invoice.get("amount_krw"))
            claimed=money(p.get("invoice_amount_krw"))
            if amount is None or claimed is None:
                status="REVIEW_AMOUNT_UNPARSEABLE"
            elif amount!=claimed:
                status="REVIEW_AMOUNT_MISMATCH"
            else:
                status="MATCHED_EXACT_ID"
            found=idx
        qlinks=quotes.get(key,[])
        result={"invoice_number":invoice.get("invoice_number"),
                "project_id":invoice.get("project_id"),"payment_index":found,
                "status":status,"quotation_links":len(qlinks)}
        results.append(result)
    # unmatched payment items are NOT considered paid; matching absence is not proof.
    used={r["payment_index"] for r in results if r["payment_index"] is not None}
    stats=dict(Counter(r["status"] for r in results))
    stats["PAYMENT_ONLY_REVIEW"]=len(payments)-len(used)
    stats["TOTAL_INVOICES"]=len(invoices)
    stats["TOTAL_PAYMENTS"]=len(payments)
    return results,stats
