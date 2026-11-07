#!/usr/bin/env python3
"""Project-to-payment handoff. No invoice-only completion or guessed bank receipts.

Feishu Project Progress Board remains the one per-project system of record.
The optional receipt columns are *not* written by the CRM sync; independent,
explicitly reviewed evidence must populate them before records are archived.
"""
import re
from decimal import Decimal, InvalidOperation

ACTIVE="PRODUCTION_ACTIVE"
PAYMENT="PAYMENT_FOLLOWUP"
ARCHIVE="PAID_ARCHIVED"

EVIDENCE_FIELDS=(
    "Payment Invoice No","Bank Receipt Reference","Verified Invoice KRW",
    "Verified Received KRW","Receipt Verified At","Receipt Verified By",
    "Receipt Source","Receipt Verification Status",
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

def verified_full_payment(evidence):
    """Receipt provenance + date + unique invoice + fully matched value required."""
    if cell(evidence,"Receipt Verification Status")!="VERIFIED":
        return False
    if cell(evidence,"Receipt Source") not in {"BANK_RECEIPT","ERP_CASH_RECEIPT"}:
        return False
    strings=("Payment Invoice No","Bank Receipt Reference","Receipt Verified At","Receipt Verified By")
    if any(not cell(evidence,k) for k in strings):
        return False
    if not re.fullmatch(r"20\d\d-\d\d-\d\d",cell(evidence,"Receipt Verified At")):
        return False
    invoice=parsed_amount(cell(evidence,"Verified Invoice KRW"))
    received=parsed_amount(cell(evidence,"Verified Received KRW"))
    return invoice is not None and received is not None and received>=invoice

def finalize(row,receipt_fields=None):
    item=dict(row)
    completion=cell(item,"Completion Evidence")
    ended=completion in {"CSS_EXPLICIT_FINAL_HANDOFF","LIFECYCLE_EXPLICIT_FINAL_HANDOFF",
                         "ALL_SUBPROJECTS_FINAL_REPORT_VERIFIED"}
    ispaid=ended and verified_full_payment(receipt_fields or {})
    if ispaid:
        item["Workflow Lane"]=ARCHIVE
        item["Payment State"]="PAID_VERIFIED"
        item["Next Action"]="입금 증빙 검증 완료 · 일반 운영 화면에서 숨김 (기록 보존)"
    elif ended:
        item["Workflow Lane"]=PAYMENT
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
