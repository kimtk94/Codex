#!/usr/bin/env python3
"""Read-only, aggregate-only SIF / Contract->PO issue diagnostics.

Never guess missing project links. No manual linking, sender mail writes,
tracker edits, customer/project identifiers, or mail content in CI output.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
import sys
import urllib.parse

import contract_po_tracker as po
import sif_evidence_tracker as sif
from jiin_crm_sif_po_audit import evidence
from mail_classification_2026 import since_2026
from qq_mail_ingest import SafeError, auth, list_all, plain_field
from setup_sales_web import EXPECTED_BASE


def original(fields, source, name):
    if name == "CRM Filtered Mail Intake" and (
        plain_field(fields.get("Source Account")) != po.CRM_ACCOUNT or
        plain_field(fields.get("Source Filter")) != "EXACT_FROM_CRM"
    ):
        return False
    subject = plain_field(fields.get("Subject")).strip()
    return bool(
        plain_field(fields.get("Mail Key")).strip()
        and po.exact_sender(fields, source)
        and plain_field(fields.get("Direction")) == "INBOUND"
        and since_2026(plain_field(fields.get("Received At")))
        and po.parse_time(plain_field(fields.get("Received At")))
        and subject and not po.REPLY.match(subject)
        and not plain_field(fields.get("In Reply To")).strip()
    )


def unlinked_reason(subject):
    amea = {x.upper() for x in po.AMEA.findall(subject)}
    fallback = {x.upper() for x in po.X_PROJECT.findall(subject)}
    fallback.update(x.upper() for x in po.H_PROJECT.findall(subject))
    if len(amea) > 1:
        return "MULTIPLE_AMEA_IN_SUBJECT"
    if not amea and len(fallback) > 1:
        return "MULTIPLE_X_H_IN_SUBJECT"
    if not amea and not fallback:
        return "NO_PROJECT_ID_IN_SUBJECT"
    # Safeguard for changes to the identifier parser.
    return "OTHER_UNRESOLVED_SUBJECT_ID"


def compute(source_rows, po_tracker_rows=None, sif_tracker_rows=None):
    po_tracker_rows = po_tracker_rows or []
    sif_tracker_rows = sif_tracker_rows or []
    source_count = Counter()
    problems = Counter()
    sif_counts = Counter()
    contract_events, sif_events, other_po_events = [], [], []
    for name, sender in po.SOURCES:
        for record in source_rows.get(name, []):
            fields = record.get("fields") or {}
            if not original(fields, sender, name):
                continue
            source_count["original_" + ("CRM" if sender == po.CRM_SENDER else "CSS")] += 1
            contract_event = po.event(fields, sender)
            if contract_event:
                other_po_events.append(contract_event)
                if contract_event["contract"]:
                    contract_events.append(contract_event)
            sif_event = sif.sif_event(fields, sender)
            if not sif_event:
                # Body-only evidence must never be promoted to an official notice.
                subject = plain_field(fields.get("Subject"))
                body = plain_field(fields.get("Body Excerpt"))
                if evidence(subject, body, "SIF") == "MENTION_ONLY":
                    problems["SIF_BODY_ONLY_MENTION_EXCLUDED"] += 1
                continue
            sif_counts["subject_sif_original_notices"] += 1
            sif_counts["subject_state_" + sif_event["state"]] += 1
            if sif_event["project"]:
                sif_events.append(sif_event)
                sif_counts["subject_notice_linked"] += 1
            else:
                sif_counts["subject_notice_unlinked"] += 1
                subject = plain_field(fields.get("Subject"))
                problems[unlinked_reason(subject)] += 1
                if po.unique_project(plain_field(fields.get("Body Excerpt"))):
                    problems["UNLINKED_WITH_BODY_IDENTIFIER_CANDIDATE_NOT_USED"] += 1

    desired_sif = sif.build_rows(contract_events, sif_events, datetime.now(timezone.utc).isoformat())
    desired_po = po.build_tracker(other_po_events, datetime.now(timezone.utc).isoformat())
    sif_status = Counter(row["SIF Status"] for row in desired_sif)
    po_notice_status = Counter(row["PO Status"] for row in desired_po)
    sif_contract_no_notice = sum(
        row["Contract Notice"] == "YES" and row["SIF Status"] == "SIF_NOT_OBSERVED"
        for row in desired_sif
    )
    po_attest = Counter()
    indexed = {}
    for row in po_tracker_rows:
        fields = row.get("fields") or {}
        project = plain_field(fields.get("Project ID")).strip()
        if not project or project in indexed:
            raise SafeError("ISSUE_AUDIT_DUPLICATE_OR_EMPTY_PO_PROJECT_ID")
        indexed[project] = row
        verified = po.manual_file_verified(fields)
        manual = any(plain_field(fields.get(k)).strip() for k in (
            "PO Document Verification", "PO Document Reference",
            "PO Verified At", "PO Verified By"))
        if verified:
            po_attest["file_attested"] += 1
        elif manual:
            po_attest["partial_or_invalid_attestation"] += 1
    desired_pids = {r["Project ID"] for r in desired_po}
    stored_ids = set(indexed)
    tracker_check = {
        "po_source_projects": len(desired_po),
        "po_tracker_rows": len(po_tracker_rows),
        "po_missing_from_tracker": len(desired_pids - stored_ids),
        "po_tracker_extra_historical_rows": len(stored_ids - desired_pids),
        "sif_source_projects": len(desired_sif),
        "sif_tracker_rows": len(sif_tracker_rows),
        "sif_tracker_count_mismatch": len(desired_sif) != len(sif_tracker_rows),
    }
    if sum(sif_status.values()) != len(desired_sif):
        raise SafeError("ISSUE_AUDIT_SIF_INTEGRITY_FAILED")
    if sum(po_notice_status.values()) != len(desired_po):
        raise SafeError("ISSUE_AUDIT_PO_INTEGRITY_FAILED")
    if sum(problems[k] for k in ("MULTIPLE_AMEA_IN_SUBJECT", "MULTIPLE_X_H_IN_SUBJECT",
                                  "NO_PROJECT_ID_IN_SUBJECT", "OTHER_UNRESOLVED_SUBJECT_ID")) != sif_counts["subject_notice_unlinked"]:
        raise SafeError("ISSUE_AUDIT_UNLINKED_BREAKDOWN_INVALID")
    return {
        "mail_sources": dict(source_count),
        "sif_notices": dict(sif_counts),
        "unlinked_reasons": dict(problems),
        "sif_project_statuses": dict(sif_status),
        "sif_contract_projects_without_notice": sif_contract_no_notice,
        "sif_approval_notice_projects": sif_status["SIF_APPROVED_NOTICE"],
        "sif_followup_projects": len(desired_sif) - sif_status["SIF_APPROVED_NOTICE"],
        "po_source_statuses": dict(po_notice_status),
        "po_file_verification": dict(po_attest),
        "tracker_sync_consistency": tracker_check,
        "policy": "NO_MANUAL_LINKING_NO_GUESSED_JOINS_READ_ONLY",
        "writes": 0,
    }


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("ISSUE_AUDIT_WRONG_BASE")
    token, root = auth()
    tables = list_all(root + "/tables", token, "sif_po_issue_tables")
    source = {}
    for name, _ in po.SOURCES:
        path = po.find_source(token, root, tables, name)
        source[name] = list_all(path + "/records", token, "sif_po_issue_source")
    tracker = {}
    for name in (po.TABLE, sif.TABLE):
        candidates = [item for item in tables if item.get("name") == name]
        if len(candidates) != 1:
            raise SafeError("ISSUE_AUDIT_TRACKER_MISSING_OR_DUPLICATE_" + name.replace(" ", "_"))
        path = root + "/tables/" + urllib.parse.quote(candidates[0]["table_id"], safe="")
        tracker[name] = list_all(path + "/records", token, "sif_po_issue_tracker")
    report = compute(source, tracker[po.TABLE], tracker[sif.TABLE])
    print("SIF_PO_ISSUES_PASS " + json.dumps(report, sort_keys=True, ensure_ascii=True))
    return report


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("SIF_PO_ISSUES_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
