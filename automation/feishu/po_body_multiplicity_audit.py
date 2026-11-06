#!/usr/bin/env python3
"""Read-only PO mail multiplicity and body excerpt analysis (2026 CSS + CRM).

Read both Subject and the *stored first 1,800 characters* of Body Excerpt.
Never conclude that a document was actually delivered, signed or approved from
a subject/body string. Do not infer a project ID from quoted body content.
Actions logs show aggregates only: no subject, ID, mail key or body contents.
"""
from collections import Counter, defaultdict
import json
import os
import re
import sys

import contract_po_tracker as po
from qq_mail_ingest import SafeError, auth, list_all, plain_field
from setup_sales_web import EXPECTED_BASE

PO_TOKEN = re.compile(r"(?<![\w])(?:PO|P\.O\.|purchase[\s-]+order)(?![\w])", re.I)
REQUEST = re.compile(
    r"\b(?:please|kindly|request(?:ed)?|need(?:ed)?|required?|submit|provide|send|share|upload|awaiting|waiting|pending|missing|remind(?:er)?|follow[\s-]*up)\b", re.I
)
NEGATED = re.compile(
    r"\b(?:not[\s-]+(?:yet[\s-]+)?received|has[\s-]+not[\s-]+been[\s-]+received|"
    r"not[\s-]+submitted|no[\s-]+po|still[\s-]+missing|without[\s-]+po)\b", re.I
)
RECEIVED = re.compile(r"\b(?:received|uploaded|submitted|attached|provided|sent)\b", re.I)
CONFIRMED = re.compile(r"\b(?:approved|accepted|confirmed)\b", re.I)
PO_NUMBER = re.compile(r"\b(?:PO[\s#:.-]*number|purchase\s+order[\s#:.-]*number|PO\s*#|P\.O\.\s*#)\b", re.I)
FILE = re.compile(r"\b(?:attach(?:ed|ment)?|file|pdf|signed|scan(?:ned)?)\b", re.I)
QUOTE = re.compile(r"(?im)^\s*(?:on .+ wrote:|from:|sent:|subject:|>+|-----original message-----)")
CUT = 1800


def contexts(body, term=PO_TOKEN, radius=100):
    """Small windows around actual PO tokens; unrelated request words ignored."""
    return [body[max(0, m.start()-radius):min(len(body), m.end()+radius)]
            for m in term.finditer(body)]


def body_signal(body):
    """Single provisional content label; never file verification."""
    body = str(body or "")
    chunks = contexts(body)
    if not chunks:
        return "NO_PO_IN_STORED_BODY"
    if any(NEGATED.search(c) for c in chunks):
        return "BODY_MISSING_OR_NOT_RECEIVED_CANDIDATE"
    if any(CONFIRMED.search(c) for c in chunks):
        return "BODY_APPROVAL_CLAIM_REVIEW"
    if any(RECEIVED.search(c) for c in chunks):
        return "BODY_DELIVERY_CLAIM_REVIEW"
    if any(REQUEST.search(c) for c in chunks):
        return "BODY_REQUEST_REMINDER_CANDIDATE"
    if any(PO_NUMBER.search(c) for c in chunks):
        return "BODY_PO_NUMBER_ONLY"
    return "BODY_MENTION_ONLY"


def classify(fields, sender, name):
    """Ignore non-original/unverified mail; no body-only identity promotion."""
    key = plain_field(fields.get("Mail Key")).strip()
    if not key or key == po.SMOKE_KEY or not po.exact_sender(fields, sender):
        return None
    if (name == "CRM Filtered Mail Intake" and
        (plain_field(fields.get("Source Account")) != po.CRM_ACCOUNT or
         plain_field(fields.get("Source Filter")) != "EXACT_FROM_CRM")):
        return None
    if plain_field(fields.get("Direction")) != "INBOUND":
        return None
    when = plain_field(fields.get("Received At"))
    if not po.since_2026(when) or not po.parse_time(when):
        return None
    subject = plain_field(fields.get("Subject")).strip()
    if not subject or po.REPLY.match(subject) or plain_field(fields.get("In Reply To")).strip():
        return None
    body = plain_field(fields.get("Body Excerpt"))
    if not PO_TOKEN.search(subject) and not PO_TOKEN.search(body):
        return None
    project = po.unique_project(subject)
    body_project = po.unique_project(body)
    subject_signal = po.document_evidence(subject, "", "PO")
    body_only = not PO_TOKEN.search(subject) and bool(PO_TOKEN.search(body))
    return {
        "project": project,
        "subject_signal": subject_signal,
        "body_signal": body_signal(body),
        "body_only": body_only,
        "body_project_candidate_untrusted": bool(not project and body_project),
        "body_near_excerpt_limit": len(body) >= CUT,
        "body_file_word_only": bool(FILE.search(body) and PO_TOKEN.search(body)),
        "quoted_fragment_detected": bool(QUOTE.search(body)),
        "sender_source": "CRM" if sender == po.CRM_SENDER else "CSS",
        "key": key,
    }


def summarize(source, tracker_ids=()):
    counters = Counter()
    groups = defaultdict(list)
    seen_keys = set()
    trusted_contract_ids = set(tracker_ids)
    for name, sender in po.SOURCES:
        for record in source.get(name, []):
            item = classify(record.get("fields") or {}, sender, name)
            if item is None:
                continue
            if item["key"] in seen_keys:
                raise SafeError("PO_BODY_DUPLICATE_MAIL_KEY")
            seen_keys.add(item["key"])
            counters["po_relevant_mail"] += 1
            counters["source_" + item["sender_source"]] += 1
            counters["subject_" + item["subject_signal"]] += 1
            counters["body_" + item["body_signal"]] += 1
            for flag in ("body_only", "body_project_candidate_untrusted",
                         "body_near_excerpt_limit", "body_file_word_only",
                         "quoted_fragment_detected"):
                counters[flag] += int(item[flag])
            if item["project"]:
                groups[item["project"]].append(item)
            else:
                counters["unlinked_no_subject_project"] += 1

    duplicates = Counter({"projects_with_po_mail": len(groups),
                          "projects_with_multiple_po_mails": sum(len(v)>1 for v in groups.values()),
                          "po_mail_in_multiple_projects": sum(len(v) for v in groups.values() if len(v)>1),
                          "max_mails_per_project": max((len(v) for v in groups.values()), default=0),
                          "subject_linked_mail": sum(len(v) for v in groups.values())})
    owned_groups = {project: msgs for project, msgs in groups.items()
                    if project in trusted_contract_ids}
    owned = {
        "owned_css_contract_projects": len(trusted_contract_ids),
        "owned_projects_with_po_mail": len(owned_groups),
        "owned_projects_without_po_mail": len(trusted_contract_ids) - len(owned_groups),
        "owned_projects_with_multiple_po_mails": sum(len(v) > 1 for v in owned_groups.values()),
        "owned_total_po_related_mails": sum(len(v) for v in owned_groups.values()),
    }
    contract = {
        "po_mails_for_existing_contracts": sum(
            len(v) for k,v in groups.items() if k in trusted_contract_ids),
        "contract_projects_with_po_mail": sum(
            k in trusted_contract_ids for k in groups),
        "po_mail_projects_without_contract": sum(
            k not in trusted_contract_ids for k in groups),
        "contract_ids_in_tracker": len(trusted_contract_ids),
    }
    return {"source": "2026 ORIGINAL CSS+CRM FEISHU BODY EXCERPT",
            "body_scope": "FIRST_1800_NORMALIZED_CHARACTERS_NOT_FULL_MAIL",
            "po_mail_categories": dict(sorted(counters.items())),
            "repeat_project_counts": dict(duplicates),
            "owned_project_counts": owned,
            "contract_context": contract,
            "document_file_verification": "NOT_ATTEMPTED_NO_ATTACHMENT_BYTES",
            "source_writes": 0, "manual_links": 0}


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("PO_BODY_WRONG_BASE")
    token, root = auth()
    tables = list_all(root+"/tables", token, "po_body_tables")
    source = {}
    for name, _ in po.SOURCES:
        path = po.find_source(token, root, tables, name)
        source[name] = list_all(path+"/records", token, "po_body_source")
    tracker = [x for x in tables if x.get("name") == po.TABLE]
    if len(tracker) != 1:
        raise SafeError("PO_BODY_TRACKER_NOT_UNIQUE")
    path = root+"/tables/"+tracker[0]["table_id"]
    records = list_all(path+"/records", token, "po_body_tracker")
    contract_ids = []
    excluded_historical = 0
    for record in records:
        fields = record.get("fields") or {}
        if plain_field(fields.get("Contract Source")) == "CSS":
            contract_ids.append(plain_field(fields.get("Project ID")).strip())
        else:
            if plain_field(fields.get("PO Followup Queue")) != "EXCLUDED_NO_OWNER_CONTRACT":
                raise SafeError("PO_BODY_OTHER_SALES_NOT_EXCLUDED")
            excluded_historical += 1
    if len(contract_ids) != len(set(contract_ids)) or any(not s for s in contract_ids):
        raise SafeError("PO_BODY_DUPLICATE_OR_EMPTY_CONTRACT_KEY")
    report = summarize(source, contract_ids)
    report["excluded_historical_other_sales_projects"] = excluded_historical
    print("PO_BODY_MULTIPLICITY_AUDIT_PASS "+json.dumps(report, ensure_ascii=True, sort_keys=True))
    return report


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("PO_BODY_MULTIPLICITY_AUDIT_FAILED="+detail, file=sys.stderr)
        sys.exit(1)
