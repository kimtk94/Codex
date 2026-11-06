#!/usr/bin/env python3
"""Read-only SIF/PO evidence audit for exact-sender CRM inbox records.

An official notice is not proof of an attached signed SIF or Purchase Order.
Never expose mail content, customer information, or project IDs in Actions logs.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
import re
import sys
import urllib.parse

import jiin_crm_filtered_ingest as crm
from jiin_crm_source_audit import summarize as verify_source
from qq_mail_ingest import SafeError, auth, list_all, plain_field
from setup_sales_web import EXPECTED_BASE

SIF = r"(?:\bSIF\b|\bsample information form\b)"
PO = r"(?:\bPO\b|\bpurchase order\b)"
REPLY = re.compile(r"^\s*(?:re|fw|fwd|reply|답장|전달|회신)\s*[:：]", re.I)
IDENTIFIERS = (
    re.compile(r"\bAMEA\d{7,}(?:-\d+)?\b", re.I),
    re.compile(r"\bX\d+SC\d+(?:-Z\d+)?\b", re.I),
    re.compile(r"\bH\d{2,}SC\d+\b", re.I),
)


def has(pattern, value):
    return bool(re.search(pattern, str(value or ""), flags=re.I))


def evidence(subject, body, kind, is_reply=False):
    """Conservative event states; never claim document verification."""
    subject, body = str(subject or ""), str(body or "")
    term = SIF if kind == "SIF" else PO
    if not (has(term, subject) or has(term, body)):
        return "NOT_OBSERVED"
    if is_reply or REPLY.match(subject) or not has(term, subject):
        return "MENTION_ONLY"
    if kind == "SIF":
        if (has(rf"{term}.{{0,45}}\b(rejected|declined|failed|invalid|revision required|not\s+(?:yet\s+)?approved|not\s+received)\b", subject)
                or has(rf"\bnot\b.{{0,25}}\b(approved|received)\b.{{0,25}}{term}", subject)):
            return "REJECTED_NOTICE"
        if has(rf"{term}.{{0,40}}\bapproved\b|\bapproved\b.{{0,40}}{term}", subject):
            return "APPROVED_NOTICE"
        if has(rf"{term}.{{0,40}}\b(received|accepted)\b|\breceived\b.{{0,40}}{term}", subject):
            return "RECEIVED_NOTICE"
        if has(rf"{term}.{{0,40}}\bsubmitted\b|\bsubmitted\b.{{0,40}}{term}", subject):
            return "SUBMITTED_NOTICE"
        if has(rf"(please|kindly|need to|required|request|awaiting|missing).{{0,50}}{term}|{term}.{{0,30}}\b(required|missing|pending|requested|needed)\b", subject):
            return "ACTION_REQUESTED"
        return "MENTION_ONLY"
    if (has(rf"{term}.{{0,45}}\b(missing|pending|awaiting|not\s+(?:yet\s+)?received|has\s+not\s+been\s+received|not\s+submitted|unavailable)\b", subject)
            or has(rf"\b(?:not|no)\b.{{0,28}}(?:\b(received|submitted)\b.{{0,25}}{term}|{term}.{{0,25}}\breceived\b)", subject)):
        return "NOT_RECEIVED_NOTICE"
    if has(rf"{term}.{{0,35}}\b(approved|accepted|confirmed)\b|\b(approved|accepted|confirmed)\b.{{0,35}}{term}", subject):
        return "CONFIRMED_NOTICE"
    if has(rf"{term}.{{0,35}}\b(received|uploaded)\b|\b(received|uploaded)\b.{{0,35}}{term}", subject):
        return "RECEIVED_NOTICE"
    if has(rf"(please|kindly|need to|required|request|awaiting).{{0,50}}{term}|{term}.{{0,30}}\b(required|requested|needed)\b", subject):
        return "ACTION_REQUESTED"
    return "MENTION_ONLY"


def project_identifier(fields):
    """Prefer unique exact IDs; never invent cross-system account joins."""
    subject = plain_field(fields.get("Subject"))
    fallback = " ".join(plain_field(fields.get(k)) for k in ("AMEA", "H Project", "Body Excerpt"))
    for text in (subject, fallback):
        for pattern in IDENTIFIERS:
            ids = {match.upper() for match in pattern.findall(text)}
            if len(ids) == 1:
                return next(iter(ids)), False
            if len(ids) > 1:
                return None, True
    return None, False


def audit_rows(rows):
    total = verify_source(rows)  # Fail closed on wrong sender, account, date, or duplicate.
    counts = {"SIF": Counter(), "PO": Counter()}
    per_project = defaultdict(lambda: {"SIF": [], "PO": []})
    unlinked, ambiguous, without_id = 0, 0, 0
    for row in rows:
        fields = row.get("fields") or {}
        subject, body = (plain_field(fields.get(k)) for k in ("Subject", "Body Excerpt"))
        is_reply = bool(plain_field(fields.get("In Reply To")))
        found = {kind: evidence(subject, body, kind, is_reply) for kind in ("SIF", "PO")}
        for kind, state in found.items():
            counts[kind][state] += 1
        project, conflict = project_identifier(fields)
        if not project:
            ambiguous += int(conflict)
            without_id += int(not conflict)
            unlinked += int(any(v != "NOT_OBSERVED" for v in found.values()))
            continue
        when = datetime.fromisoformat(plain_field(fields.get("Received At")).replace("Z", "+00:00"))
        when = when.astimezone(timezone.utc)
        for kind, state in found.items():
            if state != "NOT_OBSERVED":
                per_project[project][kind].append((when, state))
    review = 0
    for events in per_project.values():
        statuses = []
        for kind in ("SIF", "PO"):
            entries = events[kind]
            if not entries:
                statuses.append("NOT_OBSERVED")
                continue
            newest = max(t for t, _ in entries)
            choices = {v for t, v in entries if t == newest}
            statuses.append(next(iter(choices)) if len(choices) == 1 else "CONFLICT_REVIEW")
        if any(state not in ("APPROVED_NOTICE", "RECEIVED_NOTICE", "CONFIRMED_NOTICE") for state in statuses):
            review += 1
    return {
        "source_rows": total, "sif_messages": dict(counts["SIF"]),
        "po_messages": dict(counts["PO"]),
        "projects_with_sif_po_evidence": len(per_project),
        "projects_requiring_review": review,
        "unlinked_actionable_messages": unlinked,
        "multi_identifier_messages": ambiguous,
        "messages_without_identifier": without_id,
    }


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("CRM_SIF_PO_WRONG_BASE")
    token, root = auth()
    matches = [r for r in list_all(root + "/tables", token, "crm_sif_po_table")
               if r.get("name") == crm.TABLE]
    if len(matches) != 1:
        raise SafeError("CRM_SIF_PO_TABLE_NOT_UNIQUE")
    path = root + "/tables/" + urllib.parse.quote(matches[0]["table_id"], safe="")
    report = audit_rows(list_all(path + "/records", token, "crm_sif_po_records"))
    print("CRM_SIF_PO_AUDIT_PASS " + json.dumps(report, sort_keys=True, ensure_ascii=False))
    print("CRM_SIF_PO_DECISION=NOTICE_ONLY_DOCUMENT_RECEIPT_UNVERIFIED source_writes=0")
    return report


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("CRM_SIF_PO_AUDIT_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
