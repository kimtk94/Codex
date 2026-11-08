#!/usr/bin/env python3
"""Read-only Feishu grouped eTax original evidence for October manual ERP.

An eTax approval number may legitimately cover multiple ERP line items.
Do NOT count H-number duplicates as two independently issued eTax documents.
Check each ERP line's F amount and the common H group's total, original
CMS Invoice date (C), Sales label (G), remark (I), cancellation (J), and
the entire 750-row D:H membership. Do not modify Revenue or publish raw
customer information, tax approval numbers, URLs or remarks in CI logs.
"""
import datetime as dt
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
import re
import sys

from qq_mail_ingest import SafeError,auth
from etax_original_tracking_proof import read_tracking,build_index,scalar
from etax_h_semantics_audit import find_sheet,row_read,signals

TARGETS={"20910000208":1287000,"20910000209":9317000}
EXPECTED_GROUP_GROSS=sum(TARGETS.values())
EXPECTED_GROUP_NET=9640000


def parse_won(value):
    text=scalar(value).replace(",","").replace("₩","").replace("KRW","").replace(" ","")
    try: d=Decimal(text)
    except InvalidOperation:return None
    if not d.is_finite() or d!=d.to_integral_value() or d<0:return None
    return int(d)


def month_hint(value):
    text=scalar(value)
    if re.fullmatch(r"4[4-9]\d{3}(?:\.0+)?",text):
        date=dt.datetime(1899,12,30)+dt.timedelta(days=float(text))
        return date.strftime("%Y-%m")
    if re.match(r"^20\d{2}[-./]\d{1,2}[-./]\d{1,2}(?:\D|$)",text):
        m=re.match(r"^(20\d{2})[-./](\d{1,2})[-./]",text)
        if m and 1<=int(m.group(2))<=12:
            return m.group(1)+"-"+m.group(2).zfill(2)
    return "UNKNOWN"


def normalized_person(text):
    raw=scalar(text).casefold()
    return "".join(ch for ch in raw if ch.isalnum())


def sales_hint(value):
    val=normalized_person(value)
    return ("SAME_AS_USER_LABEL" if
            val in {"kimtaehoon","taehoonkim","김태훈"} else
            "DIFFERENT_OR_FORMAT_UNVERIFIED")


def evidence(values,original_rows):
    """values is an exact ERP -> full Feishu A:N row mapping."""
    if set(values)!=set(TARGETS):
        raise SafeError("ETAX_GROUP_TARGET_COVERAGE_MISSING")
    all_h={}
    for row in original_rows[1:]:
        if len(row)<5:continue
        erp=scalar(row[0])
        h=scalar(row[4])
        if erp and h:
            all_h.setdefault(h,set()).add(erp)
    detail={}
    for invoice,expected in TARGETS.items():
        row=values[invoice]
        if len(row)<10 or scalar(row[3])!=invoice:
            raise SafeError("ETAX_GROUP_ROW_IDENTITY_WRONG")
        amount=parse_won(row[5])
        cert=scalar(row[7])
        if not cert or cert not in all_h or invoice not in all_h[cert]:
            raise SafeError("ETAX_GROUP_CERT_LINK_MISSING")
        cancell=scalar(row[9])
        remarks=signals(row[8])
        detail[invoice]={
            "original_f_amount":amount,
            "expected_erp_gross":expected,
            "amount_match":amount==expected,
            "cms_month_hint":month_hint(row[2]),
            "sales_hint":sales_hint(row[6]),
            "sales_raw":scalar(row[6]),
            "remark_positive":("ISSUANCE_WORD" in remarks and
                               "NEGATIVE_OR_PENDING_WORD" not in remarks),
            "cancel_number_present":bool(cancell),
            "etax_number":cert,
            "cert_group_members":set(all_h[cert]),
            "num_digits":sum(c.isdigit() for c in cert),
        }
    c0=detail["20910000208"]["etax_number"]
    c1=detail["20910000209"]["etax_number"]
    combined_gross=sum(x["original_f_amount"] for x in detail.values()
                       if x["original_f_amount"] is not None)
    combined_net=int((Decimal(combined_gross)*Decimal(10)/Decimal(11))
                     .quantize(Decimal("1"),rounding=ROUND_HALF_UP))
    certificate_group=detail["20910000208"]["cert_group_members"]
    result={
        "same_certificate":c0==c1,
        "certificate_group_member_count":len(certificate_group),
        "certificate_group_exact_pair":certificate_group==set(TARGETS),
        "f_amounts_match":all(x["amount_match"] for x in detail.values()),
        "gross_sum":combined_gross,
        "net_sum":combined_net,
        "total_matches":combined_gross==EXPECTED_GROUP_GROSS and
                        combined_net==EXPECTED_GROUP_NET,
        "no_cancel":all(not x["cancel_number_present"] for x in detail.values()),
        "issuance_remark_positive":all(x["remark_positive"] for x in detail.values()),
        "cms_month_hints":sorted(set(x["cms_month_hint"] for x in detail.values())),
        "same_sales_label":len({x["sales_raw"] for x in detail.values()})==1,
        "source_sales_matches_user":all(x["sales_hint"]=="SAME_AS_USER_LABEL"
                                        for x in detail.values()),
        "details":detail,
    }
    result["document_proof_consistent"]=all([
        result["same_certificate"],result["certificate_group_exact_pair"],
        result["f_amounts_match"],result["total_matches"],result["no_cancel"],
        result["issuance_remark_positive"],
    ])
    return result


def main():
    token,_=auth()
    rows,_=read_tracking(token)
    index=build_index(rows)
    sid=find_sheet(token)
    proof={}
    for invoice in TARGETS:
        if invoice not in index:
            raise SafeError("ETAX_GROUP_ERP_NOT_IN_FULL_SOURCE:"+invoice)
        h,line=index[invoice]
        r=row_read(token,sid,line,line)
        if len(r)!=1 or len(r[0])<10 or scalar(r[0][7])!=h:
            raise SafeError("ETAX_GROUP_ORIGINAL_READBACK_MISMATCH")
        proof[invoice]=r[0]
    result=evidence(proof,rows)
    for invoice in TARGETS:
        x=result["details"][invoice]
        print("ETAX_GROUP_ERP_PROOF invoice="+invoice+
              " original_F_gross="+str(x["original_f_amount"])+
              " mirror_gross="+str(x["expected_erp_gross"])+
              " F_match="+str(x["amount_match"]).lower()+
              " CMS_invoice_month_hint="+x["cms_month_hint"]+
              " Sales_label="+x["sales_hint"]+
              " positive_remark="+str(x["remark_positive"]).lower()+
              " cancel_cert_present="+str(x["cancel_number_present"]).lower()+
              " eTax_cert_digits="+str(x["num_digits"])+
              " original_details_redacted=true",flush=True)
    print("ETAX_GROUP_COMBINED_CHECK same_eTax_certificate="+
          str(result["same_certificate"]).lower()+
          " original_rows_sharing_certificate="+
          str(result["certificate_group_member_count"])+
          " exact_ERP_pair="+str(result["certificate_group_exact_pair"]).lower()+
          " original_F_gross_sum="+str(result["gross_sum"])+
          " net_per_certificate_group="+str(result["net_sum"])+
          " expected_gross="+str(EXPECTED_GROUP_GROSS)+
          " expected_net="+str(EXPECTED_GROUP_NET)+
          " total_matches="+str(result["total_matches"]).lower()+
          " same_source_sales_label="+str(result["same_sales_label"]).lower()+
          " original_sales_matches_user="+
          str(result["source_sales_matches_user"]).lower()+
          " original_remark_issued="+
          str(result["issuance_remark_positive"]).lower()+
          " no_cancel_eTax_number="+str(result["no_cancel"]).lower()+
          " evidence_consistent="+
          str(result["document_proof_consistent"]).lower()+
          " original_eTax_documents=1_if_cert_valid"+
          " revenue_automatically_posted=NO",flush=True)
    if not result["document_proof_consistent"]:
        print("ETAX_GROUP_DECISION=HOLD_ORIGINAL_AMOUNT_OR_CERT_MISMATCH",flush=True)
    else:
        print("ETAX_GROUP_DECISION=ORIGINAL_ETAX_CERT_GROUP_MATCHED_"+
              "CHECK_ACCOUNTING_MONTH_AND_SFDC_OWNER_BEFORE_REVENUE",flush=True)
    print("ETAX_GROUP_AUDIT_PASS financial_writes=0 source_writes=0",flush=True)


if __name__=="__main__":
    try:main()
    except Exception as exc:
        message=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("ETAX_GROUP_AUDIT_FAILED="+message,file=sys.stderr)
        sys.exit(1)
