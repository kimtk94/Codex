#!/usr/bin/env python3
"""Latest dated Feishu Payment Receipt + Outstanding invoice reconciliation.

Read-only pure transformation of the previously synchronized dated Feishu
worksheets. No arbitrary name or amount-only matching. Aggregated/bundled
receipts are REVIEW, not fully settled. Intended to feed native Feishu Base.
"""
import datetime as dt
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

FRESHNESS_HOURS=72
PAYMENT_SOURCES=("Payment Receipt","Payment Outstanding","eTax Invoice")
# Exact sales ledger label; never include another salesperson via fuzzy name.
PERSONAL_SALES_LABEL="Kim Taehoon"
OWNER_MATCH="MY_VERIFIED"
OWNER_OTHER="OTHER_SALES"
OWNER_REVIEW="OWNER_UNVERIFIED"
REQUIRED_RECEIPTS={"Deposit Date","Amount (KRW)","CMS No.",
                   "Date","Amount","CMS No. [2]",
                   "Date [2]","Amount [2]","CMS No. [3]"}
REQUIRED_INVOICE={"CMS Invoice Num","Quotation Number","Project Number","Amount","Sales"}
REQUIRED_OUT={"CMS Invoice Number","Quotation Number","Project Number","Invoice Amount","Balance","Sales"}
INVOICE_RE=re.compile(r"\d{10,15}\Z")
AMEA_RE=re.compile(r"AMEA\d{10}\Z")
X_RE=re.compile(r"X\d+SC\d+(?:-Z\d+)?\Z")

def norm(row,k):
    return str((row or {}).get(k) or "").strip()
def money(v,positive=False):
    text=str(v or "").replace(",","").replace("₩","").strip()
    try:value=Decimal(text)
    except InvalidOperation:return None
    if not value.is_finite() or value<0 or (positive and value==0):
        return None
    return value

def date_str(raw):
    raw=str(raw or "").strip()
    if not raw:return ""
    if re.fullmatch(r"\d{5}",raw):
        n=int(raw)
        if not 41000<=n<=70000:return ""
        return (dt.date(1899,12,30)+dt.timedelta(days=n)).isoformat()
    for fmt in ("%Y-%m-%d","%Y/%m/%d","%d-%b-%Y","%d-%b-%y","%d/%m/%Y"):
        try:return dt.datetime.strptime(raw,fmt).date().isoformat()
        except ValueError:pass
    return ""

def ensure_headers(rows,required,name):
    if not isinstance(rows,list):raise ValueError("MISSING_"+name)
    if rows and required.issubset(rows[0].keys()):return
    raise ValueError("BAD_SCHEMA_"+name)

def source_dates(manifest,now=None):
    now=now or dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    dates={}
    for row in manifest:
        key=norm(row,"Source")
        if key not in PAYMENT_SOURCES:continue
        if key in dates:raise ValueError("DUPLICATE_MANIFEST_SOURCE")
        source_date=norm(row,"Source Date")
        synced=norm(row,"Synced At KST")
        if norm(row,"Schema")!="HEADER_MATCHED":
            raise ValueError("PAYMENT_SOURCE_HEADER_NOT_VERIFIED")
        try:
            stamp=dt.datetime.fromisoformat(synced)
            day=dt.date.fromisoformat(source_date)
        except ValueError:raise ValueError("PAYMENT_MANIFEST_DATE_INVALID") from None
        if stamp.tzinfo is None or not 0<=(now-stamp).total_seconds()<=FRESHNESS_HOURS*3600:
            raise ValueError("PAYMENT_SOURCE_MIRROR_STALE")
        if day>now.date() or (now.date()-day).days>45:
            raise ValueError("PAYMENT_SOURCE_DATE_STALE")
        dates[key]=source_date
    if set(dates)!=set(PAYMENT_SOURCES):raise ValueError("PAYMENT_SOURCE_MANIFEST_INCOMPLETE")
    return dates

def exact_sales_name(name):
    # Whitespace variation only, no substring or ambiguous nickname matching.
    return " ".join(str(name or "").split()).casefold()

def invoice_owner(invoices):
    if not invoices:return OWNER_REVIEW
    owners=set()
    for invoice in invoices:
        invoice_owners=invoice["owners"]
        if not invoice_owners:return OWNER_REVIEW
        owners.update(invoice_owners)
    if owners=={exact_sales_name(PERSONAL_SALES_LABEL)}:
        return OWNER_MATCH
    if exact_sales_name(PERSONAL_SALES_LABEL) in owners:
        return OWNER_REVIEW
    return OWNER_OTHER


def invoice_map(etax,outstanding):
    """Use official CMS+AMEA+X+VAT-gross exact linkage, never customer names."""
    ensure_headers(etax,REQUIRED_INVOICE,"ETAX")
    ensure_headers(outstanding,REQUIRED_OUT,"OUTSTANDING")
    by_number={}
    conflicts=set()
    def insert(no,amea,x,amount,source,sales,balance=None):
        if not (INVOICE_RE.fullmatch(no) and AMEA_RE.fullmatch(amea)
                and X_RE.fullmatch(x) and amount is not None):
            return
        key=(amea,x,amount)
        prev=by_number.get(no)
        if prev is not None and (prev["project"],prev["x"],prev["amount"])!=key:
            conflicts.add(no)
            return
        if prev is None:
            by_number[no]={"project":amea,"x":x,"amount":amount,
                           "sources":set(),"owners":set(),"balance":None}
        if not exact_sales_name(sales):
            # Unknown ownership remains review-only, even if a different
            # source happens to have a sales tag.
            by_number[no]["owner_incomplete"]=True
        else:by_number[no]["owners"].add(exact_sales_name(sales))
        by_number[no]["sources"].add(source)
        if balance is not None:
            by_number[no]["balance"]=balance
    for r in etax:
        insert(norm(r,"CMS Invoice Num"),norm(r,"Quotation Number").upper(),
               norm(r,"Project Number").upper(),money(norm(r,"Amount"),True),
               "ETAX",norm(r,"Sales"))
    for r in outstanding:
        insert(norm(r,"CMS Invoice Number"),norm(r,"Quotation Number").upper(),
               norm(r,"Project Number").upper(),money(norm(r,"Invoice Amount"),True),
               "OUTSTANDING",norm(r,"Sales"),money(norm(r,"Balance")))
    for no in conflicts:by_number.pop(no,None)
    return by_number,conflicts

def receipt_map(rows):
    ensure_headers(rows,REQUIRED_RECEIPTS,"RECEIPTS")
    evidence=defaultdict(list)
    ambiguous=set()
    seen=set()
    fields=(("CMS No.","Amount (KRW)","Deposit Date"),
            ("CMS No. [2]","Amount","Date"),
            ("CMS No. [3]","Amount [2]","Date [2]"))
    for row in rows:
        for cms_field,amount_field,date_field in fields:
            raw=norm(row,cms_field)
            if not raw:continue
            invoices=[x.strip() for x in re.split(r"[,;\n]+",raw) if x.strip()]
            ids=[v for v in invoices if INVOICE_RE.fullmatch(v)]
            if len(ids)!=1 or len(invoices)!=1:
                ambiguous.update(ids)
                continue
            inv=ids[0]
            amount=money(norm(row,amount_field),True)
            date=date_str(norm(row,date_field))
            if not amount or not date:
                ambiguous.add(inv)
                continue
            event=(inv,str(amount),date)
            if event in seen:
                ambiguous.add(inv)
                continue
            seen.add(event)
            evidence[inv].append((amount,date))
    return evidence,ambiguous

def build_payment_evidence(sources,manifest,now=None):
    """Return exact receipt proof, invoice/balance context, and aggregate counts."""
    dates=source_dates(manifest,now)
    invoices,invoice_conflicts=invoice_map(
        sources.get("Feishu Latest eTax",[]),
        sources.get("Feishu Latest Outstanding",[]))
    receipts,receipt_conflicts=receipt_map(sources.get("Feishu Latest Receipts",[]))
    groups=defaultdict(list)
    for number,inv in invoices.items():
        groups[inv["project"]].append((number,inv))
    matched={}
    billing={}
    diagnostics={"projects_with_invoices":len(groups),
                 "my_verified_invoice_projects":0,
                 "other_sales_invoice_projects":0,
                 "owner_review_projects":0,
                 "projects_source_receipt_complete":0,
                 "invoice_conflicts":len(invoice_conflicts),
                 "receipt_ambiguities":len(receipt_conflicts),
                 "projects_review_required":0}
    for pid,items in groups.items():
        checks=[]
        for no,inv in items:
            deposits=receipts.get(no,[])
            amt=sum((x for x,_ in deposits),Decimal("0"))
            outstanding=inv["balance"]
            # Positive outstanding balances override receipt candidates until
            # the newer Outstanding ledger catches up.
            clear=(bool(deposits) and no not in receipt_conflicts and
                   amt==inv["amount"] and
                   (outstanding is None or outstanding==0))
            checks.append((no,inv,amt,deposits,clear))
        # Outstanding balance is unknown if the invoice is absent from the
        # dated Outstanding snapshot, not zero or paid by inference.
        current_balances=[inv["balance"] for _,inv,_,_,_ in checks]
        gross_total=sum((inv["amount"] for _,inv,_,_,_ in checks),Decimal("0"))
        owner=invoice_owner([inv for _,inv in items])
        if any(inv.get("owner_incomplete") for _,inv in items):
            owner=OWNER_REVIEW
        if owner==OWNER_MATCH:diagnostics["my_verified_invoice_projects"]+=1
        elif owner==OWNER_OTHER:diagnostics["other_sales_invoice_projects"]+=1
        else:diagnostics["owner_review_projects"]+=1
        billing[pid]={
            "Payment Owner Scope":owner,
            "Payment Invoice No":";".join(sorted(no for no,_,_,_,_ in checks)),
            "Invoice Gross KRW":int(gross_total),
            "Outstanding Source Snapshot Date":dates["Payment Outstanding"],
        }
        if current_balances and all(x is not None for x in current_balances):
            billing[pid]["Outstanding Balance KRW"]=int(sum(current_balances,Decimal("0")))
        if not checks or not all(c[4] for c in checks):
            diagnostics["projects_review_required"]+=1
            continue
        invoice_sum=sum((i["amount"] for _,i,_,_,_ in checks),Decimal("0"))
        received_sum=sum((amt for _,_,amt,_,_ in checks),Decimal("0"))
        if invoice_sum<=0 or received_sum!=invoice_sum:continue
        all_dates=[date for _,_,_,v,_ in checks for _,date in v]
        matched[pid]={
            "Payment Invoice No":";".join(sorted(no for no,_,_,_,_ in checks)),
            "Bank Receipt Reference":";".join(sorted(no+"@"+date for no,_,_,deposits,_ in checks for _,date in deposits)),
            "Verified Invoice KRW":int(invoice_sum),
            "Verified Received KRW":int(received_sum),
            "Receipt Verified At":max(all_dates),
            "Receipt Verified By":"AUTO_FEISHU_EXACT_CMS_AMOUNT",
            "Receipt Source":"FEISHU_LATEST_PAYMENT_RECEIPT",
            "Receipt Verification Status":"SOURCE_EXACT_VERIFIED",
            "Receipt Source Snapshot Date":dates["Payment Receipt"],
            "Outstanding Source Snapshot Date":dates["Payment Outstanding"],
        }
        diagnostics["projects_source_receipt_complete"]+=1
    return matched,billing,diagnostics
