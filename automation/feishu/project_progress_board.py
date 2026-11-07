#!/usr/bin/env python3
"""Pure, source-backed Feishu project progress board projector.

No API writes. Exact AMEA and (when unambiguous) Feishu X project joins only.
The CSS original project description is shown as a fallback but is not
misrepresented as a verified Salesforce quotation name.
"""
import collections
import re
from project_settlement import completion_evidence, finalize


def value(row, key):
    return str((row or {}).get(key) or "").strip()


def percent(raw):
    s = str(raw or "").strip().rstrip("%").replace(",", "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if v != v or not 0 <= v <= 100:
        return None
    return round(v, 1)


def bar(v):
    if v is None:
        return "미확인"
    units = min(10, max(0, round(v / 10)))
    return "█" * units + "░" * (10 - units) + "  " + f"{v:g}%"


def physical(stage):
    text = str(stage or "").lower()
    return bool(re.search(r"sif|sample|\bqc\b|library|sequenc|production|data ready|final report|completed", text)) and not bool(re.search(r"invoice issued|statement confirmed", text))


def exact_records(rows, col):
    index = collections.defaultdict(list)
    for r in rows:
        k = value(r, col).upper()
        if k:
            index[k].append(r)
    return index


def has_prepayment_flag(record):
    return value(record, "Prepayment").upper() in {"TRUE", "YES", "1"}


def prepare_project_board(sources, project_rows):
    sif_index = exact_records(sources.get("CSS Contract-SIF Tracker", []), "project_id")
    css_index = exact_records(sources.get("CSS Project Dashboard", []), "project_id")
    quote_index = exact_records(sources.get("Quote Portfolio", []), "Approved AMEA ID")
    life_index = exact_records(sources.get("BI Project Lifecycle Overview", []), "AMEA")
    prepay_quotation = exact_records(sources.get("Feishu Latest Prepayments", []), "Quotation Number")
    prepay_x = exact_records(sources.get("Feishu Latest Prepayments", []), "Project Number")
    output = []

    for row in project_rows:
        pid = value(row, "AMEA").upper()
        if not re.fullmatch(r"AMEA\d{7,}(?:-\d{1,3})?", pid):
            continue
        css_items = css_index.get(pid, [])
        css = css_items[0] if len(css_items) == 1 else {}
        sif_items = sif_index.get(pid, [])
        sif = sif_items[0] if len(sif_items) == 1 else {}
        lifecycles = life_index.get(pid, [])

        verified_quotes = sorted({
            value(q, "Quote Name")
            for q in quote_index.get(pid, [])
            if value(q, "Quote Name") and value(q, "Active").upper() in {"ACTIVE", "YES"}
            and value(q, "Approval Match").upper() == "APPROVED"
        })
        if len(verified_quotes) == 1:
            quote_name = verified_quotes[0]
            quote_state = "SFDC_EXACT_VERIFIED"
        elif len(verified_quotes) > 1:
            quote_name = "\n".join(verified_quotes)
            quote_state = "MULTIPLE_QUOTE_REVIEW"
        else:
            quote_name = (value(sif, "AMEA Full Name") or value(css, "project_description")
                          or value(row, "Project"))
            quote_state = "CSS_ORIGINAL_UNVERIFIED" if quote_name else "NOT_LINKED"

        # A prepayment may be identified by the exact AMEA quotation ID.
        # X-base fallback is valid only when all lifecycle subprojects for an
        # AMEA have the same X base. An unrelated quoted X never transfers.
        base_x = set()
        for lifecycle in lifecycles:
            hit = re.fullmatch(r"(X\d+SC\d+)(?:-Z\d+)?", value(lifecycle, "Project / Sub-project").upper())
            if hit:
                base_x.add(hit.group(1))
        x_pre = bool(len(base_x) == 1 and prepay_x.get(next(iter(base_x))))
        prepay = has_prepayment_flag(sif) or bool(prepay_quotation.get(pid)) or x_pre
        prepay_evidence = (
            "CSS_PREPAYMENT_FLAG" if has_prepayment_flag(sif)
            else "FEISHU_EXACT_QUOTE" if prepay_quotation.get(pid)
            else "FEISHU_UNIQUE_X" if x_pre else "NOT_VERIFIED"
        )

        evidence = (value(sif, "Status") + " " + value(sif, "workflow_status")).lower()
        approved = bool(re.search(r"sif\s*(?:approved|승인)", evidence))
        submitted = approved or bool(re.search(r"sif\s*(?:submitted|received|제출|접수)", evidence)) or bool(value(sif, "sif_first_seen_at"))
        sif_state = (
            "APPROVED" if approved else "SUBMITTED" if submitted
            else "WAIVED_PREPAYMENT" if prepay else value(row, "SIF State") or "NOT_VERIFIED"
        )
        pct = percent(row.get("Progress %"))
        stage = value(css, "current_stage") or value(row, "Current Stage")
        # The existing CSS snapshot may contain administrative billing
        # milestones; invoice-only milestones cannot prove physical progress.
        if not physical(stage):
            if pct is not None and stage and re.search(r"invoice|statement", stage, re.I):
                pct = None
            elif pct is None:
                pct = None

        # A later physical milestone defeats an older SIF reminder.
        next_action = value(row, "Next Action")
        if prepay and not submitted:
            next_action = "SIF 면제(Prepayment) · 샘플 입고/실제 진행 단계 확인"
        elif submitted and (not next_action or re.search(r"SIF", next_action, re.I)):
            next_action = "SIF 접수 확인 · 샘플 입고/후속 공정 확인"
        elif pct is not None and pct >= 40 and re.search(r"SIF", next_action, re.I):
            next_action = "이전 SIF 알림 제외 · 실제 생산 단계 확인"

        lifecycle_po = any(re.search(r"final report|statement\s+(?:ready|confirmation)", value(x, "CSS Stage (legacy)"), re.I)
                           for x in lifecycles)
        po_state = "REPORT_STATEMENT_INFERRED" if lifecycle_po else "PO_ORIGINAL_NOT_VERIFIED"
        # No false PO receipt claim; future tracker evidence can override this.
        result = {
            "Source Key": value(row, "Source Key"),
            "Project Display Name": (quote_name.replace("\n"," / ")+" | "+pid),
            "Completion Evidence": completion_evidence(stage,lifecycles),
            "AMEA": pid,
            "Quote Full Name": quote_name,
            "Quote Match State": quote_state,
            "Institution": value(row, "Institution"),
            "Customer": value(row, "Customer"),
            "Service": value(row, "Service"),
            "Current Stage": stage or "미확인",
            "Progress Bar": bar(pct),
            "Prepayment": "YES" if prepay else "NOT_VERIFIED",
            "Prepayment Evidence": prepay_evidence,
            "SIF State": sif_state,
            "PO Evidence": po_state,
            "Next Action": next_action or "현재 단계 확인",
            "Evidence": value(row, "Evidence"),
        }
        if pct is not None:
            result["Progress %"] = pct
        output.append(finalize(result))
    if len(output) != len({x["Source Key"] for x in output}):
        raise ValueError("DUPLICATE_BOARD_SOURCE_KEY")
    return output
