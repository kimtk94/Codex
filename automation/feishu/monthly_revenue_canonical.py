#!/usr/bin/env python3
"""Authoritative issued Revenue months for Feishu Monthly Tax Invoice.

VAT-inclusive invoices and VAT-exclusive Revenue are distinct measures.
Pending/forecast cash never becomes issued Revenue. The canonical monthly
snapshot must reconcile with both the independent lifecycle gross and the
explicit 2026 Revenue Source Authority audit, not a stale legacy CSS ledger.
"""
import datetime as dt
import decimal
import re
from zoneinfo import ZoneInfo

D=decimal.Decimal


class RevenueEvidenceError(RuntimeError):
    pass


def cell(row,name):
    return str(row.get(name) or "").strip()


def money(value,kind):
    raw=str(value or "").strip().replace(",","").replace("₩","").replace("KRW","").replace(" ","")
    try:
        amount=D(raw)
    except decimal.InvalidOperation as e:
        raise RevenueEvidenceError("CANONICAL_"+kind+"_INVALID") from e
    if not amount.is_finite() or amount<0 or amount!=amount.to_integral_value():
        raise RevenueEvidenceError("CANONICAL_"+kind+"_INVALID")
    return int(amount)


def positive_count(row,name):
    amount=money(cell(row,name),"COUNT")
    if amount<=0:raise RevenueEvidenceError("CANONICAL_INVOICE_COUNT_INVALID")
    return amount


def valid_month(month):
    return bool(re.fullmatch(r"20\d\d-(?:0[1-9]|1[0-2])",month))


def unique_months(rows,field):
    by={}
    for row in rows:
        month=cell(row,"Month")
        if not valid_month(month):
            raise RevenueEvidenceError("CANONICAL_"+field+"_MONTH_INVALID")
        if month in by:raise RevenueEvidenceError("CANONICAL_"+field+"_DUPLICATE_MONTH")
        by[month]=row
    return by


def verified_at(value):
    try:
        stamp=dt.datetime.strptime(value,"%Y-%m-%d %H:%M:%S KST")
    except ValueError as e:
        raise RevenueEvidenceError("CANONICAL_VERIFIED_TIMESTAMP_INVALID") from e
    if stamp>dt.datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)+dt.timedelta(minutes=10):
        raise RevenueEvidenceError("CANONICAL_VERIFIED_IN_FUTURE")
    return value


def evidence_rows(source,fx=D("1500")):
    if fx<=0:raise RevenueEvidenceError("CANONICAL_REPORTING_FX_INVALID")
    mandatory=("BI Revenue Net VAT Monthly","BI Revenue Lifecycle Monthly","Revenue Source Authority")
    if any(not source.get(name) for name in mandatory):
        raise RevenueEvidenceError("CANONICAL_MANDATORY_SOURCE_MISSING")
    netrows=unique_months(source[mandatory[0]],"NET")
    grossrows=unique_months(source[mandatory[1]],"GROSS")
    auth={}
    for row in source[mandatory[2]]:
        month=cell(row,"Month")
        if not valid_month(month):raise RevenueEvidenceError("CANONICAL_AUTH_MONTH_INVALID")
        role=cell(row,"Source Role")
        if role not in {"CANONICAL_ISSUED_NET","CANONICAL_ACTUAL_GROSS"}:
            continue
        key=(month,role)
        if key in auth:raise RevenueEvidenceError("CANONICAL_AUTH_DUPLICATE")
        auth[key]=row
    result=[]
    for month,row in sorted(netrows.items(),reverse=True):
        gross=money(cell(row,"Issued Invoice Gross KRW (VAT incl)"),"GROSS")
        net=money(cell(row,"Issued Net Revenue KRW (VAT excl)"),"NET")
        count=money(cell(row,"Issued Invoice Count"),"COUNT")
        if gross==0 and net==0 and count==0:
            # A future forecast-only month is NOT an issued-revenue data point.
            continue
        if min(gross,net,count)<=0:
            raise RevenueEvidenceError("CANONICAL_PARTIAL_ISSUED_MONTH")
        if abs(D(gross)-D(net)*D("1.1"))>D("3"):
            raise RevenueEvidenceError("CANONICAL_VAT_PARITY_MISMATCH")
        if cell(row,"Evidence State").split(";")[0]!="INVOICE_FILENAME_VERIFIED_NET":
            raise RevenueEvidenceError("CANONICAL_NET_NOT_VERIFIED")
        snapshot=verified_at(cell(row,"Verified At KST"))
        other=grossrows.get(month)
        if other is None or (money(cell(other,"Actual Invoice KRW"),"GROSS")!=gross or
                             money(cell(other,"Invoice Count"),"COUNT")!=count):
            raise RevenueEvidenceError("CANONICAL_LIFECYCLE_GROSS_COUNT_MISMATCH")
        for role,basis,status,expected,amount in [
                ("CANONICAL_ISSUED_NET","VAT_EXCLUDED","MATCHED_TO_INVOICE_SOURCE",
                 "BI Revenue Net VAT Monthly",net),
                ("CANONICAL_ACTUAL_GROSS","VAT_INCLUDED","MATCHED_TO_NET_AUDIT",
                 "BI Revenue Lifecycle Monthly",gross)]:
            row_auth=auth.get((month,role))
            if (row_auth is None or cell(row_auth,"Source Tab")!=expected or
                    cell(row_auth,"Authoritative For KPI")!="YES" or
                    cell(row_auth,"Tax Basis")!=basis or
                    cell(row_auth,"Source Parity")!=status):
                raise RevenueEvidenceError("CANONICAL_AUTHORITY_NOT_ESTABLISHED")
            if (money(cell(row_auth,"Amount KRW"),"AUTH_AMOUNT")!=amount or
                    money(cell(row_auth,"Issued Invoice Count"),"AUTH_COUNT")!=count):
                raise RevenueEvidenceError("CANONICAL_AUTHORITY_PARITY_MISMATCH")
            verified_at(cell(row_auth,"Verified KST"))
        reported=cell(row,"Issued Net Revenue kUSD @1500")
        try:published_k=D(reported)
        except decimal.InvalidOperation as e:
            raise RevenueEvidenceError("CANONICAL_KUSD_INVALID") from e
        calculated_k=D(net)/fx/D(1000)
        if abs(published_k-calculated_k)>D("0.002"):
            raise RevenueEvidenceError("CANONICAL_KUSD_FX_MISMATCH")
        k=calculated_k.quantize(D("0.0001"))
        m=(D(net)/D(1000000)).quantize(D("0.0001"))
        result.append({
            "Source Key":"INVOICE:"+month,"Month":month,
            "Invoice Count":count,
            "Tax Invoice KRW Incl VAT":gross,
            "Net Revenue KRW Ex VAT":net,
            "Net Revenue M KRW":int(m) if m==m.to_integral_value() else float(m),
            "Net Revenue K USD":int(k) if k==k.to_integral_value() else float(k),
            # The legacy CSS Invoice Monthly Summary has explicitly been
            # rejected as a source for these months. Clear its old values.
            "CSS Source Invoice Count":None,
            "CSS Source KRW Incl VAT":None,
            "Source Difference KRW":None,
            # Audit signs the *QQ-issued CMS subset*, not the completeness
            # of the sales owner's billing portfolio. Manual ERP invoices are
            # outside the 209126... original-email parser and some QQ backfill
            # invoices still lack independently verified salesperson ownership.
            # Distinguish valid subtotal math from complete October revenue.
            "Coverage Status":"QQ_ISSUED_VERIFIED_ERP_MANUAL_SCOPE_REVIEW",
            "Evidence":"BI Revenue Net VAT Monthly / BI Revenue Lifecycle Monthly / "+
                "Revenue Source Authority; issued QQ CMS invoice subset only; "+
                snapshot+"; VAT gross independently reconciled; "+
                "manual ERP billing and unmatched QQ owner/issuance pending "+
                "separate review; pending/forecast excluded."
        })
    if not result:
        raise RevenueEvidenceError("CANONICAL_NO_ISSUED_MONTHS")
    return result
