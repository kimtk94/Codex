#!/usr/bin/env python3
"""Contract-gated PO project gap audit — strict 1 project = 1 decision.

Uses verified original CSS/CRM 2026 source records and existing PO tracker rows.
Only messages with unambiguous IDs in SUBJECT may be joined to a project.
A delivery/approval phrase in the stored body is an unverified review lead,
NEVER proof of receiving a PO file. No source, tracker, or mailbox writes.
Outputs aggregate numbers only, never project identifiers or mail content.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
import sys
import urllib.parse

import contract_po_tracker as po
import po_body_multiplicity_audit as body
from qq_mail_ingest import SafeError, auth, list_all, plain_field
from setup_sales_web import EXPECTED_BASE

RECEIPT_BODY = {"BODY_DELIVERY_CLAIM_REVIEW", "BODY_APPROVAL_CLAIM_REVIEW"}
RECEIPT_SUBJECT = {"RECEIVED_NOTICE", "CONFIRMED_NOTICE"}
NEGATIVE_BODY = {"BODY_MISSING_OR_NOT_RECEIVED_CANDIDATE"}
REQUEST_BODY = {"BODY_REQUEST_REMINDER_CANDIDATE"}
NEGATIVE_SUBJECT = {"NOT_RECEIVED_NOTICE"}
REQUEST_SUBJECT = {"ACTION_REQUESTED"}
ORDER = ("POSITIVE_CANDIDATE", "MISSING_OR_NOT_RECEIVED",
         "REQUEST_OR_REMINDER", "MENTION_ONLY")


def classify_event(item):
    """Negative notice supersedes a body receipt claim within the same mail."""
    s, b = item["subject_signal"], item["body_signal"]
    if s in NEGATIVE_SUBJECT or b in NEGATIVE_BODY:
        return "MISSING_OR_NOT_RECEIVED"
    if s in RECEIPT_SUBJECT or b in RECEIPT_BODY:
        return "POSITIVE_CANDIDATE"
    if s in REQUEST_SUBJECT or b in REQUEST_BODY:
        return "REQUEST_OR_REMINDER"
    return "MENTION_ONLY"


def project_rows(source, tracker_records):
    contracts = {}
    for rec in tracker_records:
        fields = rec.get("fields") or {}
        project = plain_field(fields.get("Project ID")).strip()
        created = po.parse_time(plain_field(fields.get("Contract Notice UTC")))
        contract_key = plain_field(fields.get("Contract Mail Key")).strip()
        if not project or project in contracts or not created or not contract_key:
            raise SafeError("PO_GAP_CONTRACT_TRACKER_INVALID")
        queue = plain_field(fields.get("PO Followup Queue")).strip() or "NOT_YET_SYNCED"
        inference = plain_field(fields.get("Submission Inference")).strip()
        if queue == "PO_SUBMITTED_INFERRED":
            downstream_at = po.parse_time(plain_field(fields.get("Downstream Evidence UTC")))
            evidence_type = plain_field(fields.get("Downstream Evidence Type")).strip()
            evidence_key = plain_field(fields.get("Downstream Mail Key")).strip()
            if (inference != "ASSUMED_BY_DOWNSTREAM_NOTICE" or
                not downstream_at or downstream_at <= created or
                evidence_type not in ("FINAL_REPORT", "STATEMENT",
                                      "FINAL_REPORT_AND_STATEMENT") or
                not evidence_key or po.manual_file_verified(fields)):
                raise SafeError("PO_GAP_INFERRED_SUBMISSION_PROOF_INVALID")
        contracts[project] = {"created": created, "key": contract_key,
                              "mail_status": plain_field(fields.get("PO Status")),
                              "followup_queue": queue,
                              "inference": inference,
                              "manual_verified": po.manual_file_verified(fields)}

    grouped = defaultdict(list)
    seen = set()
    stats = Counter()
    for name, sender in po.SOURCES:
        for rec in source.get(name, []):
            fields = rec.get("fields") or {}
            msg = body.classify(fields, sender, name)
            if msg is None:
                continue
            key = msg["key"]
            if key in seen:
                raise SafeError("PO_GAP_SOURCE_MAIL_DUPLICATE")
            seen.add(key)
            project = msg["project"]
            if not project:
                stats["po_mail_without_subject_project"] += 1
                continue
            if project not in contracts:
                stats["po_mail_outside_contract_tracker"] += 1
                continue
            stats["po_mail_subject_joined_to_contract"] += 1
            at = po.parse_time(plain_field(fields.get("Received At")))
            contract = contracts[project]
            if at < contract["created"] or key == contract["key"]:
                stats["before_contract_or_contract_notice"] += 1
                continue
            if at == contract["created"]:
                stats["same_timestamp_as_contract_different_mail"] += 1
                # This is not provably after Contract; do not count as post-Contract.
                continue
            grouped[project].append({
                "at": at, "classification": classify_event(msg),
                "source": msg["sender_source"],
                "body_only": msg["body_only"],
                "body_excerpt_near_limit": msg["body_near_excerpt_limit"],
                "body_attachment_word": msg["body_file_word_only"],
                "key": key,
            })

    counts = Counter()
    for project, contract in contracts.items():
        counts["all_contract_projects"] += 1
        counts["existing_mail_status_" + (contract["mail_status"] or "UNKNOWN")] += 1
        counts["followup_" + contract["followup_queue"]] += 1
        counts["file_attested"] += int(contract["manual_verified"])
        events = grouped.get(project, [])
        if not events:
            counts["no_post_contract_po_mail"] += 1
            continue
        counts["projects_with_post_contract_po_mail"] += 1
        counts["post_contract_po_mail_total"] += len(events)
        counts["projects_post_contract_repeated_po_mail"] += int(len(events) > 1)
        counts["projects_body_only_po_after_contract"] += int(any(e["body_only"] for e in events))
        counts["projects_body_excerpt_limit_after_contract"] += int(any(e["body_excerpt_near_limit"] for e in events))
        counts["projects_positive_ever_after_contract"] += int(
            any(e["classification"] == "POSITIVE_CANDIDATE" for e in events)
        )
        counts["projects_missing_ever_after_contract"] += int(
            any(e["classification"] == "MISSING_OR_NOT_RECEIVED" for e in events)
        )
        counts["projects_request_ever_after_contract"] += int(
            any(e["classification"] == "REQUEST_OR_REMINDER" for e in events)
        )
        latest_at = max(e["at"] for e in events)
        latest_types = {e["classification"] for e in events if e["at"] == latest_at}
        if len(latest_types) > 1:
            counts["latest_conflicting_notice"] += 1
            continue
        latest = next(iter(latest_types))
        counts["latest_" + latest] += 1
        if latest == "POSITIVE_CANDIDATE":
            counts["potential_review_queue_reduction_not_verified"] += 1
            latest_positive = [e for e in events
                               if e["at"] == latest_at and e["classification"] == latest]
            counts["latest_positive_body_attachment_word"] += int(
                any(e["body_attachment_word"] for e in latest_positive))
            counts["latest_positive_near_excerpt_limit"] += int(
                any(e["body_excerpt_near_limit"] for e in latest_positive))
            counts["latest_positive_crm_source"] += int(
                any(e["source"] == "CRM" for e in latest_positive))
    if counts["all_contract_projects"] != (
        counts["no_post_contract_po_mail"] + counts["projects_with_post_contract_po_mail"]
    ):
        raise SafeError("PO_GAP_COHORT_PARTITION_INVALID")
    if counts["projects_with_post_contract_po_mail"] != (
        counts["latest_conflicting_notice"] +
        sum(counts["latest_" + state] for state in ORDER)
    ):
        raise SafeError("PO_GAP_LATEST_PARTITION_INVALID")
    return {
        "project_cohorts": dict(sorted(counts.items())),
        "mail_matching": dict(sorted(stats.items())),
        "review_candidate_reduction": counts["potential_review_queue_reduction_not_verified"],
        "operational_po_missing_projects": counts["followup_PO_REQUIRED"],
        "inferred_po_submitted_projects": counts["followup_PO_SUBMITTED_INFERRED"],
        "verified_receipt_reduction": counts["file_attested"],
        "policy": "CONTRACT_CREATED_THEN_POST_CONTRACT_ORIGINAL_SUBJECT_ID_ONLY",
        "action": "READ_ONLY_NO_STATUS_CHANGES_NO_MANUAL_LINKS",
        "writes": 0,
    }


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("PO_GAP_WRONG_FEISHU_BASE")
    token, root = auth()
    tables = list_all(root + "/tables", token, "po_gap_tables")
    source = {}
    for name, _ in po.SOURCES:
        path = po.find_source(token, root, tables, name)
        source[name] = list_all(path + "/records", token, "po_gap_source")
    found = [t for t in tables if t.get("name") == po.TABLE]
    if len(found) != 1:
        raise SafeError("PO_GAP_TRACKER_TABLE_MISSING_OR_DUPLICATE")
    path = root + "/tables/" + urllib.parse.quote(found[0]["table_id"], safe="")
    tracker = list_all(path + "/records", token, "po_gap_tracker")
    result = project_rows(source, tracker)
    print("PO_PROJECT_GAP_AUDIT_PASS " + json.dumps(result, ensure_ascii=True, sort_keys=True))
    return result


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("PO_PROJECT_GAP_AUDIT_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
