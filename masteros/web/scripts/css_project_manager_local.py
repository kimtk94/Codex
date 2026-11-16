#!/usr/bin/env python3
"""Quote-first local project manager built from bounded, read-only Google mirrors.

X/subproject ID is unique; AMEA is a many-to-one relation. Never infer a
Salesforce Quote Name from an unrelated CSS project description. Never mark a
receipt as paid without actual receipt evidence. No remote server or writes.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter, defaultdict
from urllib.parse import quote as url_quote

from css_projects_local import KST, session, when

SOURCE_BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
CSS_BOOK = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
MAX_PROJECTS = 1500
COMPLETION_RE = re.compile(r"final\s*report|statement\s*(?:ready|confirm)|completed|finished|deliver(?:ed|y)", re.I)
# Finance transition must come from current Feishu state, not an older CSS email.
FEISHU_FINANCE_STAGE = re.compile(
    r"^(?:waiting\s+for\s+settlement|settled|project\s+completed|completed)$", re.I)
RECEIPT_NOT_PROVED = "결제 증빙 미확인"
STAGE_ORDER = ("계약/SIF", "샘플/QC", "라이브러리", "시퀀싱", "데이터/리포트", "공정 미확인")


def clean(value):
    return str(value).strip() if value is not None else ""


def table(rows, required, name):
    if not rows or not isinstance(rows[0], list) or not set(required).issubset(rows[0]):
        raise ValueError("SCHEMA_" + name)
    if len(rows) > 15002:
        raise ValueError("ROW_LIMIT_" + name)
    headers = rows[0]
    return [dict(zip(headers, (clean(x) for x in row))) for row in rows[1:] if row]


def latest(rows, key):
    values = [when(row.get(key)) for row in rows]
    return max((v for v in values if v is not None), default=None)


def iso(value):
    return value.isoformat() if value else None


def yes(value):
    return clean(value).upper() in {"YES", "TRUE", "1"}


def stage_group(stage):
    text = clean(stage).lower()
    if re.search(r"data ready|download|final report|statement|report ready|deliv", text):
        return "데이터/리포트"
    if re.search(r"sequenc|nova\s*seq|production", text):
        return "시퀀싱"
    if re.search(r"library|\blib\b", text):
        return "라이브러리"
    if re.search(r"sample|receiv|\bqc\b|quality control", text):
        return "샘플/QC"
    if re.search(r"contract|\bsif\b|\bpo\b", text):
        return "계약/SIF"
    return "공정 미확인"


def progress_value(raw):
    try:
        value = float(clean(raw).rstrip("%"))
    except ValueError:
        return None
    return round(value, 1) if 0 <= value <= 100 else None


def create_project(row, quotes, sifs, payments, quote_candidates=None):
    project_id = clean(row.get("Project / Sub-project"))
    amea = clean(row.get("AMEA")).upper()
    if not project_id:
        raise ValueError("MISSING_PROJECT_ID")
    matches = quotes.get(amea, [])
    candidates = (quote_candidates or {}).get(amea, [])
    candidate_names = sorted({x["Quotation Name"] for x in candidates
                              if clean(x.get("Quotation Name"))})
    names = sorted({q["Quote Name"] for q in matches})
    if len(names) == 1:
        quote_name, quote_state = names[0], "APPROVED_AMEA_MIRROR"
    elif len(names) > 1:
        quote_name, quote_state = "", "MULTIPLE_QUOTE_REVIEW"
    else:
        quote_name, quote_state = "", "QUOTE_UNLINKED"
    sif_entries = sifs.get(amea, [])
    sif = sif_entries[0] if len(sif_entries) == 1 else {}
    prepayment = any(yes(s.get("Prepayment")) for s in sif_entries)
    submitted = any(clean(s.get("sif_first_seen_at")) or
                    re.search(r"sif\s*(?:submitted|approved|received|접수|제출|승인)",
                              clean(s.get("Status")) + " " + clean(s.get("workflow_status")), re.I)
                    for s in sif_entries)
    sif_state = ("제출 확인" if submitted else "Prepayment 예외" if prepayment
                 else "다중 기록 검토" if len(sif_entries) > 1 else "제출 근거 미확인")
    stage = clean(row.get("Feishu Status (latest)")) or "미확인"
    legacy_stage = clean(row.get("CSS Stage (legacy)"))
    completed = bool(FEISHU_FINANCE_STAGE.fullmatch(stage))
    legacy_completed = bool(COMPLETION_RE.search(legacy_stage))
    legacy_conflict = legacy_completed and not completed
    classification = "PAYMENT" if completed else "ACTIVE"
    # Feishu payment status is an X-level mirror, not an independently verified receipt.
    payment_rows = payments.get(project_id, [])
    if not payment_rows:
        base_x = re.sub(r"-Z\d+$", "", project_id, flags=re.I)
        alt = payments.get(base_x, [])
        if len(alt) == 1:
            payment_rows = alt
    outstanding = (payment_rows[0].get("Payment outstanding", "") if len(payment_rows) == 1
                   else "UNKNOWN")
    invoice_count = clean(row.get("Invoice Count")) or "0"
    report_statement = bool(re.search(r"final\s*report|statement", legacy_stage, re.I))
    po_state = "Report/Statement 근거로 제출 간주" if report_statement else "PO 원문 미확인"
    if classification == "PAYMENT":
        next_action = ("미수금 확인 및 결제 팔로업" if outstanding.upper() == "YES"
                       else "Invoice/Payment 증빙 확인")
    elif prepayment and not submitted:
        next_action = "Prepayment: SIF 반복 요청 제외, 샘플·공정 확인"
    elif submitted:
        next_action = "SIF 이후 샘플·QC·생산 공정 확인"
    elif sif_entries:
        next_action = "SIF 접수 또는 실제 다음 공정 확인"
    else:
        next_action = "계약·SIF·프로젝트 원문 연결 검토"
    if legacy_conflict:
        next_action = "과거 CSS 완료 vs 현재 Feishu 상태 충돌 · 현재 공정 확인"
    elif candidate_names and not quote_name:
        next_action = "Quote 승인·Active·원문 링크 확인 · " + next_action
    if stage_group(stage) == "공정 미확인" and not completed:
        next_action = "Feishu 원본 공정 확인 · " + next_action
    reasons = []
    if not quote_name:
        reasons.append("QUOTE_CANDIDATE_UNVERIFIED" if candidate_names else "QUOTE_NOT_FOUND")
    if legacy_conflict:
        reasons.append("LEGACY_COMPLETION_CONFLICT")
    if len(sif_entries) > 1:
        reasons.append("SIF_DUPLICATE_SOURCE")
    if stage.lower() in {"", "abnormal", "미확인", "unknown", "not_in_feishu_source"}:
        reasons.append("FEISHU_STAGE_UNVERIFIED")
    if outstanding.upper() == "UNKNOWN":
        reasons.append("PAYMENT_MIRROR_UNKNOWN")
    is_review = bool(reasons)
    return {
        "project_id": project_id, "amea": amea, "quote_name": quote_name,
        "quote_match_state": quote_state,
        "quote_candidate_name": candidate_names[0] if len(candidate_names) == 1 and not quote_name else "",
        "quote_candidate_state": ("UNVERIFIED_APPROVAL_DEDUP" if len(candidate_names) == 1 and not quote_name
                                  else "MULTIPLE_CANDIDATES" if len(candidate_names) > 1 and not quote_name
                                  else "NONE"),
        "quote_candidate_count": len(candidate_names) if not quote_name else 0,
        "institution": clean(row.get("Institution")) or clean(sif.get("Institution")),
        "contact": clean(row.get("Customer")) or clean(sif.get("Customer Name")),
        "service": clean(row.get("Service")), "stage": stage,
        "legacy_stage": legacy_stage, "stage_group": stage_group(stage),
        "progress_percent": progress_value(row.get("CSS Progress %")),
        "progress_source": "CSS_LEGACY_MIRROR" if progress_value(row.get("CSS Progress %")) is not None else "NOT_VERIFIED",
        "sample_count": clean(row.get("Sample Count")),
        "expected_completion": clean(row.get("Feishu Expected Completion")),
        "invoice_count": invoice_count,
        "outstanding_state": outstanding or "UNKNOWN",
        "receipt_state": RECEIPT_NOT_PROVED,
        "sif_state": sif_state, "prepayment": prepayment,
        "po_state": po_state, "next_action": next_action,
        "bucket": classification, "needs_review": is_review,
        "review_reasons": reasons,
        "legacy_completion_conflict": legacy_conflict,
        "completion_source": "FEISHU_STAGE_MIRROR" if completed else "NO_CURRENT_FINANCE_STAGE",
        "source_scope": "GOOGLE_MIRROR_ONLY",
    }


def assemble(lifecycle, quote_rows, sif_rows, pay_rows, manifest, mail, now=None,
             approval_rows=None):
    now = now or dt.datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    projects = table(lifecycle, ["Project / Sub-project", "AMEA", "Feishu Status (latest)",
                                 "CSS Stage (legacy)", "CSS Progress %"], "LIFECYCLE")
    quotes = table(quote_rows, ["Approved AMEA ID", "Quote Name", "Active", "Approval Match"],
                   "QUOTE")
    sifs = table(sif_rows, ["AMEA No.", "Prepayment", "Status", "sif_first_seen_at"], "SIF")
    pays = table(pay_rows, ["Project ID", "Payment outstanding", "Last verified KST"], "PAYMENT")
    approvals = (table(approval_rows, ["AMEA Quotation ID", "Quotation Name",
                                      "Approved AND Active", "Link Verification"], "APPROVAL_DEDUP")
                 if approval_rows is not None else [])
    manifests = table(manifest, ["Source", "Synced At KST"], "MANIFEST")
    if not 1 <= len(projects) <= MAX_PROJECTS or len({p["Project / Sub-project"] for p in projects}) != len(projects):
        raise ValueError("PROJECT_COUNT_OR_DUPLICATES")
    manifest_items = [r for r in manifests if r["Source"] == "Online-Project"]
    if len(manifest_items) != 1:
        raise ValueError("ONLINE_MANIFEST_MISSING")
    source_at = when(manifest_items[0]["Synced At KST"])
    if not mail or len(mail) < 2 or len(mail[1]) < 2:
        raise ValueError("MAIL_MANIFEST_MISSING")
    mail_at, mail_state = when(mail[1][0]), clean(mail[1][1])
    if mail_state not in ("WINDOW_CAUGHT_UP", "WINDOW_PARTIAL", "PARTIAL", "WINDOW_PENDING"):
        raise ValueError("MAIL_SCOPE_UNKNOWN")
    quote_index, sif_index, pay_index = defaultdict(list), defaultdict(list), defaultdict(list)
    candidate_index = defaultdict(list)
    for record in approvals:
        if record["AMEA Quotation ID"] and record["Quotation Name"]:
            # Approval text and a guessed Quote name are only review evidence.
            # NEVER promote without authenticated SFDC Active/Quote linkage.
            candidate_index[record["AMEA Quotation ID"].upper()].append(record)
    for record in quotes:
        if (record["Approved AMEA ID"] and record["Quote Name"]
            and record["Approval Match"].upper() == "APPROVED"
            and record["Active"].upper() in {"ACTIVE", "YES"}):
            quote_index[record["Approved AMEA ID"].upper()].append(record)
    for record in sifs:
        if record["AMEA No."]:
            sif_index[record["AMEA No."].upper()].append(record)
    for record in pays:
        if record["Project ID"]:
            pay_index[record["Project ID"]].append(record)
    result = [create_project(row, quote_index, sif_index, pay_index, candidate_index)
              for row in projects]
    # Quote identity missing/ambiguous is a REVIEW queue; does not erase physical stage.
    sync_age = (now - source_at).total_seconds()/3600 if source_at else None
    mail_age = (now - mail_at).total_seconds()/3600 if mail_at else None
    recent = all(t is not None and -0.2 <= t <= 36 for t in (sync_age, mail_age))
    status = ("STALE" if not recent else
              "PARTIAL_MIRROR" if mail_state != "WINDOW_CAUGHT_UP" else
              "PASS_MIRROR_ONLY")
    return {
        "status": status, "scope": "GOOGLE_MIRRORS_NOT_ORIGINAL_FEISHU_QQ_SFDC",
        "checked_at": now.isoformat(), "source_synced_at": iso(source_at),
        "mail_synced_at": iso(mail_at), "mail_window_state": mail_state,
        "quote_mirror_latest_at": iso(latest(quotes, "Source Timestamp")),
        "sif_mirror_latest_at": iso(latest(sifs, "updated_at")),
        "payment_mirror_latest_at": iso(latest(pays, "Last verified KST")),
        "original_feishu_verified": False, "original_qq_verified": False,
        "sfdc_live_verified": False, "payment_receipt_verified": False,
        "counts": {
            "total": len(result), "active": sum(p["bucket"] == "ACTIVE" for p in result),
            "payment": sum(p["bucket"] == "PAYMENT" for p in result),
            "review": sum(p["needs_review"] for p in result),
            "quote_linked": sum(bool(p["quote_name"]) for p in result),
            "unpaid_yes": sum(p["outstanding_state"].upper() == "YES" for p in result),
            "archive": 0,
            "quote_review_candidates": sum(p["quote_candidate_state"] == "UNVERIFIED_APPROVAL_DEDUP"
                                           for p in result),
            "quote_not_found": sum(p["quote_match_state"] == "QUOTE_UNLINKED"
                                   and not p["quote_candidate_count"] for p in result),
            "legacy_stage_conflicts": sum(p["legacy_completion_conflict"] for p in result),
            "finance_handoff_mirror": sum(p["completion_source"] == "FEISHU_STAGE_MIRROR"
                                         for p in result),
        },
        "stage_counts": dict(Counter(p["stage_group"] for p in result)),
        "project_rows": result,
    }


def fetch_values(client, book, name, bounds):
    uri = ("https://sheets.googleapis.com/v4/spreadsheets/" + book +
           "/values/" + url_quote("'" + name.replace("'", "''") + "'!" + bounds, safe="!'"))
    response = client.get(uri, timeout=28)
    response.raise_for_status()
    return response.json().get("values", [])


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-only", action="store_true",
                        help="CI-safe counts and evidence flags only; no customer fields")
    args = parser.parse_args()
    try:
        client = session()
        bundle = [
            fetch_values(client, SOURCE_BOOK, "BI Project Lifecycle Overview", "A1:Q1500"),
            fetch_values(client, SOURCE_BOOK, "Quote Portfolio", "A1:P2500"),
            fetch_values(client, CSS_BOOK, "CSS Contract-SIF Tracker", "A1:AL1000"),
            fetch_values(client, SOURCE_BOOK, "Feishu Project Status", "A1:L2000"),
            fetch_values(client, SOURCE_BOOK, "Feishu Source Manifest", "A1:G30"),
            fetch_values(client, SOURCE_BOOK, "CSS Mail Backfill Status", "A1:L5"),
        ]
        approvals = fetch_values(client, SOURCE_BOOK, "Quote Approval Dedup", "A1:Q650")
        payload = assemble(*bundle, approval_rows=approvals)
    except Exception as exc:
        payload = {
            "status": "SOURCE_UNAVAILABLE", "error_type": type(exc).__name__,
            "project_rows": [], "counts": {}, "original_feishu_verified": False,
            "payment_receipt_verified": False,
        }
    if args.summary_only:
        payload = {k: payload.get(k) for k in (
            "status", "scope", "source_synced_at", "mail_synced_at",
            "mail_window_state", "quote_mirror_latest_at", "sif_mirror_latest_at",
            "payment_mirror_latest_at", "original_feishu_verified",
            "original_qq_verified", "sfdc_live_verified",
            "payment_receipt_verified", "counts", "stage_counts", "error_type")}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    # A scheduled check may not report green when a source is missing,
    # old, or only partially collected. Customer rows remain suppressed.
    if args.summary_only and payload.get("status") != "PASS_MIRROR_ONLY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
