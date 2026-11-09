#!/usr/bin/env python3
"""Review-only, historical corroboration of owner Opportunity -> Quote absence.

Checks independent 2026-10-24 Salesforce Quote Export against current
QQ-delivered reports. A historical Salesforce ID is evidence in the old export,
NEVER proof the current Salesforce object exists, is Active or has been saved.
Do not write individual customers, opportunities or Quote IDs to CI artifacts.
"""
from collections import Counter, defaultdict
import datetime as dt
import re

from three_report_owner_scope import OWNER_NAME, norm_owner

PRIORITY_STAGES = ("Quotation Issued", "Proposal Sent", "Closed Won")
SF_RECORD = re.compile(r"^[a-zA-Z0-9]{18}$")
DATE_FORMAT = "%Y-%m-%d %H:%M:%S KST"
KST = dt.timezone(dt.timedelta(hours=9))


def historic_export_audit(rows, checked_at=None):
    """Validate IDs and source dates before attempting secondary evidence matching."""
    checked_at = checked_at or dt.datetime.now(dt.timezone.utc)
    if checked_at.tzinfo is None:
        raise ValueError("AUDIT_CLOCK_MUST_BE_OFFSET_AWARE")
    if not isinstance(rows, list) or not rows:
        raise ValueError("HISTORICAL_SFDC_QUOTE_EXPORT_MISSING")
    quote_ids, records, received = set(), set(), []
    by_opp = defaultdict(list)
    for r in rows:
        qid = str(r.get("AMEA Quotation ID", "")).strip()
        sfid = str(r.get("Salesforce Record ID", "")).strip()
        oppid = str(r.get("Opportunity ID", "")).strip()
        stamp = str(r.get("Exported At KST", "")).strip()
        if not qid or not sfid or not oppid or not stamp:
            raise ValueError("HISTORIC_QUOTE_ID_OR_PROVENANCE_MISSING")
        if not SF_RECORD.fullmatch(sfid):
            raise ValueError("HISTORIC_SF_RECORD_ID_MALFORMED")
        if qid in quote_ids or sfid in records:
            raise ValueError("HISTORIC_QUOTE_DUPLICATE_ID")
        try:
            moment = dt.datetime.strptime(stamp, DATE_FORMAT).replace(tzinfo=KST)
        except ValueError:
            raise ValueError("HISTORIC_QUOTE_DATE_INVALID") from None
        if moment.astimezone(dt.timezone.utc) > checked_at.astimezone(dt.timezone.utc):
            raise ValueError("HISTORIC_QUOTE_FUTURE_TIMESTAMP")
        quote_ids.add(qid)
        records.add(sfid)
        received.append(moment)
        by_opp[oppid].append(r)
    return {
        "indexed": by_opp,
        "quote_ids": quote_ids,
        "record_ids": records,
        "oldest_export": min(received).isoformat(),
        "latest_export": max(received).isoformat(),
        "rows": len(rows),
    }


def compare_owner_priority(opportunities, staged_quotations, historic_quotes,
                           owner=OWNER_NAME, checked_at=None):
    """Fail closed for broken IDs; never infer a live Quote absence from a snapshot."""
    if not owner or not norm_owner(owner):
        raise ValueError("OWNER_NOT_SPECIFIED")
    if not isinstance(opportunities, list) or not opportunities:
        raise ValueError("OPPORTUNITY_REPORT_EMPTY")
    if not isinstance(staged_quotations, list) or not staged_quotations:
        raise ValueError("QUOTATION_REPORT_EMPTY")
    old = historic_export_audit(historic_quotes, checked_at)

    source_opp = {}
    for r in opportunities:
        oid = str(r.get("Opportunity ID", "")).strip()
        if not oid or oid in source_opp:
            raise ValueError("OPPORTUNITY_ID_MISSING_OR_DUPLICATE")
        source_opp[oid] = r

    source_qids = set()
    source_opp_links = set()
    qid_to_opps = defaultdict(set)
    for r in staged_quotations:
        qid = str(r.get("SFDC Quotation ID", "")).strip()
        oid = str(r.get("Opportunity ID", "")).strip()
        if not qid:
            raise ValueError("QUOTATION_PRIMARY_ID_MISSING")
        source_qids.add(qid)
        if oid:
            source_opp_links.add(oid)
            qid_to_opps[qid].add(oid)

    owner_opp_unlinked = {
        oid: r for oid, r in source_opp.items()
        if norm_owner(r.get("Opportunity Owner")) == norm_owner(owner)
        and oid not in source_opp_links
    }
    priority = {
        oid: r for oid, r in owner_opp_unlinked.items()
        if str(r.get("Stage", "")).strip() in PRIORITY_STAGES
    }
    priority_stages = Counter(str(r["Stage"]).strip() for r in priority.values())
    history_confirmed = Counter()
    historic_absent = Counter()
    historic_quote_records = 0
    conflicting_quote_opportunity = 0
    old_qids_absent_current = 0
    active_old_rows = 0
    for oid, r in priority.items():
        stage = str(r.get("Stage", "")).strip()
        matched = old["indexed"].get(oid, [])
        if matched:
            history_confirmed[stage] += 1
            historic_quote_records += len(matched)
            for entry in matched:
                qid = entry["AMEA Quotation ID"].strip()
                if qid not in source_qids:
                    old_qids_absent_current += 1
                elif oid not in qid_to_opps[qid]:
                    conflicting_quote_opportunity += 1
                if str(entry.get("IsActive", "")).strip() == "1":
                    active_old_rows += 1
        else:
            historic_absent[stage] += 1
    if sum(priority_stages.values()) != len(priority):
        raise ValueError("PRIORITY_STAGE_COUNT_MISMATCH")
    if sum(history_confirmed.values()) + sum(historic_absent.values()) != len(priority):
        raise ValueError("HISTORIC_PRIORITY_CLASSIFICATION_MISMATCH")

    overlap = len(old["quote_ids"] & source_qids)
    if conflicting_quote_opportunity:
        classification = "BLOCK_CONFLICTING_STAGED_QID_RELATION"
    else:
        classification = "PASS_HISTORICAL_CORROBORATION_ONLY"
    return {
        "owner": owner,
        "source_opportunity_count": len(opportunities),
        "source_quote_distinct_ids": len(source_qids),
        "owner_without_staged_quote_opportunities": len(owner_opp_unlinked),
        "priority_opportunity_count": len(priority),
        "priority_by_stage": dict(sorted(priority_stages.items())),
        "priority_with_historic_record_id": sum(history_confirmed.values()),
        "priority_without_historic_record_id": sum(historic_absent.values()),
        "priority_historic_matches_by_stage": dict(sorted(history_confirmed.items())),
        "priority_no_historic_evidence_by_stage": dict(sorted(historic_absent.items())),
        "historical_record_ids_linked_to_priority": historic_quote_records,
        "historical_quote_ids_absent_in_current_export_for_priority": old_qids_absent_current,
        "historical_quote_report_active_1_at_export": active_old_rows,
        "historic_quote_opportunity_conflict_count": conflicting_quote_opportunity,
        "historical_export_records": old["rows"],
        "historical_export_unique_quote_ids": len(old["quote_ids"]),
        "historical_export_unique_sf_record_ids": len(old["record_ids"]),
        "historical_export_quote_ids_also_in_latest_staging": overlap,
        "historical_export_quote_ids_absent_from_latest_staging": len(old["quote_ids"]) - overlap,
        "historical_export_oldest_kst": old["oldest_export"],
        "historical_export_latest_kst": old["latest_export"],
        "review_status": classification,
        "owner_priority_live_sf_objects_verified": 0,
        "latest_sf_quote_exists_certified": False,
        "latest_sf_quote_active_certified": False,
        "historic_export_is_live_sfdc_api": False,
        "candidate_without_old_evidence_is_not_proof_of_absence": True,
        "sf_object_write_count": 0,
        "customer_mail_send_count": 0,
    }
