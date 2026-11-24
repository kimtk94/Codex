#!/usr/bin/env python3
"""Project-to-payment handoff. No invoice-only completion or guessed bank receipts.

Feishu Project Progress Board remains the one per-project system of record.
Bank/ERP attestations are user-owned. Automated receipt evidence must be
reconciled against the current source snapshot before records are archived.
"""
import re
from decimal import Decimal, InvalidOperation

ACTIVE="PRODUCTION_ACTIVE"
PAYMENT="PAYMENT_FOLLOWUP"
ARCHIVE="PAID_ARCHIVED"
SOURCE_RECEIPT="FEISHU_LATEST_PAYMENT_RECEIPT"
SOURCE_RECHECK_STATUS="SOURCE_RECHECK_REQUIRED"

EVIDENCE_FIELDS=(
    "Payment Invoice No","Bank Receipt Reference","Verified Invoice KRW",
    "Verified Received KRW","Receipt Verified At","Receipt Verified By",
    "Receipt Source","Receipt Verification Status",
    "Receipt Source Snapshot Date","Outstanding Source Snapshot Date",
)

def cell(fields,name):
    v=(fields or {}).get(name)
    if isinstance(v,list):
        return "".join(cell(x,"text") if isinstance(x,dict) else str(x) for x in v).strip()
    if isinstance(v,dict):
        return str(v.get("text") or v.get("value") or "").strip()
    return str(v if v is not None else "").strip()

def complete_event(value):
    """Only explicit final handoff evidence, not raw percentage or invoicing."""
    text=re.sub(r"[_-]+"," ",str(value or "")).strip().lower()
    return bool(
        re.search(r"\bfinal\s+report\b.{0,38}\b(ready|issued|released|sent|delivered|completed|confirmed)\b",text)
        or re.search(r"\b(final\s+report|statement)\s*(?:&|and)\s*(final\s+report|statement)\s*ready\b",text)
        or re.search(r"\bstatement\s+(ready|confirmed|issued|sent|completed)\b",text)
        or re.fullmatch(r"(?:project\s+)?(?:completed|finished|closed|delivered)",text)
    )

def completion_evidence(css_stage,lifecycle_rows):
    records=[str(x or "") for x in [css_stage]]
    stages=[
        cell(row,"CSS Stage (legacy)") or cell(row,"Feishu Status (latest)")
        for row in (lifecycle_rows or [])
    ]
    # With multiple independently progressing X sub-projects, a single final
    # report cannot close the whole AMEA. Keep it active until all are complete.
    if len(stages)>1:
        if stages and all(complete_event(s) for s in stages):
            return "ALL_SUBPROJECTS_FINAL_REPORT_VERIFIED"
        if any(complete_event(s) for s in stages):
            return "PARTIAL_SUBPROJECT_COMPLETION_REVIEW"
        if complete_event(css_stage):
            return "MULTIPLE_SUBPROJECTS_COMPLETION_REVIEW"
        return "NOT_VERIFIED"
    if complete_event(css_stage):return "CSS_EXPLICIT_FINAL_HANDOFF"
    if stages and complete_event(stages[0]):return "LIFECYCLE_EXPLICIT_FINAL_HANDOFF"
    return "NOT_VERIFIED"

def parsed_amount(value):
    try:
        v=Decimal(str(value or "").replace(",","").strip())
        return v if v.is_finite() and v>0 else None
    except (ValueError,InvalidOperation):
        return None

def manual_receipt(evidence):
    """User-owned bank/ERP evidence, including drafts awaiting verification."""
    return cell(evidence,"Receipt Source") in {"BANK_RECEIPT","ERP_CASH_RECEIPT"}

def verified_full_payment(evidence):
    """Source-exact receipt or independently signed bank/ERP evidence only."""
    status=cell(evidence,"Receipt Verification Status")
    source=cell(evidence,"Receipt Source")
    manual=status=="VERIFIED" and manual_receipt(evidence)
    automatic=(status=="SOURCE_EXACT_VERIFIED" and
        source==SOURCE_RECEIPT and
        cell(evidence,"Receipt Verified By")=="AUTO_FEISHU_EXACT_CMS_AMOUNT" and
        all(re.fullmatch(r"20\d\d-\d\d-\d\d",cell(evidence,k))
            for k in ("Receipt Source Snapshot Date","Outstanding Source Snapshot Date")))
    if not manual and not automatic:return False
    strings=("Payment Invoice No","Bank Receipt Reference","Receipt Verified At","Receipt Verified By")
    if any(not cell(evidence,k) for k in strings):return False
    if not re.fullmatch(r"20\d\d-\d\d-\d\d",cell(evidence,"Receipt Verified At")):
        return False
    invoice=parsed_amount(cell(evidence,"Verified Invoice KRW"))
    received=parsed_amount(cell(evidence,"Verified Received KRW"))
    return invoice is not None and received is not None and received==invoice


def finalize(row,receipt_fields=None):
    item=dict(row)
    completion=cell(item,"Completion Evidence")
    ended=completion in {"CSS_EXPLICIT_FINAL_HANDOFF","LIFECYCLE_EXPLICIT_FINAL_HANDOFF",
                         "ALL_SUBPROJECTS_FINAL_REPORT_VERIFIED"}
    receipt_fields=receipt_fields or {}
    verified=verified_full_payment(receipt_fields)
    manual=manual_receipt(receipt_fields)
    positive_balance=parsed_amount(cell(item,"Outstanding Balance KRW")) is not None
    # An attestation for an older invoice set cannot close newly added invoices.
    # Compare only explicit current CMS/gross context; absence is not a conflict.
    current_invoices={x.strip() for x in cell(item,"Payment Invoice No").split(";") if x.strip()}
    receipt_invoices={x.strip() for x in cell(receipt_fields,"Payment Invoice No").split(";") if x.strip()}
    current_gross=parsed_amount(cell(item,"Invoice Gross KRW"))
    manual_scope_conflict=manual and verified and (
        bool(current_invoices and current_invoices!=receipt_invoices) or
        (current_gross is not None and
         current_gross!=parsed_amount(cell(receipt_fields,"Verified Invoice KRW"))))
    ispaid=ended and verified and not positive_balance and not manual_scope_conflict
    if ispaid:
        item["Workflow Lane"]=ARCHIVE
        source_exact=cell(receipt_fields,"Receipt Verification Status")=="SOURCE_EXACT_VERIFIED"
        item["Payment State"]="PAID_SOURCE_MATCHED" if source_exact else "PAID_VERIFIED"
        item["Next Action"]=(
            "최신 Payment Receipt 원본 대조 완료 · 결제 목록에서 숨김 (원본 보관)"
            if source_exact else
            "입금 증빙 검증 완료 · 일반 운영 화면에서 숨김 (기록 보존)"
        )
    elif ended:
        item["Workflow Lane"]=PAYMENT
        if manual and positive_balance:
            item["Payment State"]="MANUAL_RECEIPT_OUTSTANDING_REVIEW"
            item["Next Action"]="수동 입금 증빙 보존 · 최신 미수 잔액과 불일치 확인 (보관 보류)"
        elif manual_scope_conflict:
            item["Payment State"]="MANUAL_RECEIPT_INVOICE_REVIEW"
            item["Next Action"]="수동 입금 증빙 보존 · 최신 Invoice 번호/총액 범위 재확인 (보관 보류)"
        elif cell(receipt_fields,"Receipt Verification Status")==SOURCE_RECHECK_STATUS:
            item["Payment State"]="SOURCE_RECEIPT_RECHECK_REQUIRED"
            item["Next Action"]="최신 Payment Receipt / Outstanding 원본 재대조 필요 · 과거 자동 증빙 보관 보류"
        elif verified and positive_balance:
            item["Payment State"]="RECEIPT_OUTSTANDING_REVIEW"
            item["Next Action"]="입금 증빙과 최신 미수 잔액 불일치 확인 (보관 보류)"
        else:
            item["Payment State"]="PAYMENT_EVIDENCE_REVIEW" if any(
                cell(receipt_fields,k) for k in EVIDENCE_FIELDS
            ) else "RECEIPT_NOT_VERIFIED"
            item["Next Action"]="프로젝트 완료 · Invoice / 입금 증빙 확인"
    else:
        item["Workflow Lane"]=ACTIVE
        item["Payment State"]="NOT_YET_DUE_OR_NOT_VERIFIED"
        if completion in {"PARTIAL_SUBPROJECT_COMPLETION_REVIEW",
                          "MULTIPLE_SUBPROJECTS_COMPLETION_REVIEW"}:
            item["Next Action"]="하위 프로젝트별 완료 증빙 검토 · 전체 종료 전환 보류"
    return item

def counts(rows):
    states={ACTIVE:0,PAYMENT:0,ARCHIVE:0}
    for row in rows:
        lane=row.get("Workflow Lane")
        if lane not in states:raise ValueError("UNRECOGNIZED_LANE")
        states[lane]+=1
    return states
