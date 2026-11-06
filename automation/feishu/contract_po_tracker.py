#!/usr/bin/env python3
"""Contract-triggered PO queue from original CSS/CRM notices in Feishu.

A contract notice starts PO follow-up. Explicit PO notices update the mail-only
status. User-directed business rule: a later Final Report Ready or Statement
Ready/Issued/Confirmed notice means PO submission is assumed for the due-list.
This is not independent proof of a received/signed PO file. Write ONLY the
dedicated Contract PO Tracker table; never mutate original mail tables.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import os
import re
import sys
import urllib.parse

from jiin_crm_filtered_ingest import ACCOUNT as CRM_ACCOUNT, SENDER as CRM_SENDER
from jiin_crm_sif_po_audit import evidence as document_evidence
from mail_classification_2026 import CSS, since_2026, email_set
from qq_mail_ingest import SafeError, SMOKE_KEY, api, auth, get_fields, list_all, plain_field
from setup_sales_web import EXPECTED_BASE, BASE_URL, list_views

TABLE = "Contract PO Tracker"
FIELDS = (
    "Project ID", "PO Status", "Contract Notice UTC", "Contract Source",
    "Contract Mail Key", "Last PO Notice UTC", "PO Notice Source",
    "PO Mail Key", "Next Action", "Evidence Rule", "Last Sync UTC",
    "PO Followup Queue", "PO Document Verification", "PO Document Reference",
    "PO Verified At", "PO Verified By",
    "Downstream Evidence Type", "Downstream Evidence UTC", "Downstream Source",
    "Downstream Mail Key", "Submission Inference",
)
SOURCES = (("QQ Mail Intake", CSS), ("CRM Filtered Mail Intake", CRM_SENDER))
AMEA = re.compile(r"\bAMEA\d{7,}(?:-\d+)?\b", re.I)
X_PROJECT = re.compile(r"\bX\d+SC\d+(?:-Z\d+)?\b", re.I)
H_PROJECT = re.compile(r"\bH\d{2,}SC\d+\b", re.I)
CONTRACT_CREATED = re.compile(
    r"\bcontract\b.{0,35}\b(created|generated|ready)\b"
    r"|\b(created|generated)\b.{0,35}\bcontract\b", re.I
)
CONTRACT_NEGATIVE = re.compile(
    r"\bcontract\b.{0,35}\b(not\s+(?:yet\s+)?ready|cancelled|canceled|void|failed|rejected)\b"
    r"|\bnot\s+(?:yet\s+)?created\b.{0,35}\bcontract\b", re.I
)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|답장|전달|회신)\s*[:：]", re.I)
FINAL_REPORT_TITLE = re.compile(r"\bfinal[\s_-]*report\b", re.I)
STATEMENT_TITLE = re.compile(r"\bstatement\b", re.I)
DOWNSTREAM_READY = re.compile(
    r"\b(?:ready|available|released|completed|delivered|issued|"
    r"confirmed|download(?:able)?|uploaded|sent)\b", re.I
)
DOWNSTREAM_NEGATIVE = re.compile(
    r"\b(?:not\s+(?:yet\s+)?(?:ready|available|released|completed|"
    r"delivered|issued|confirmed|uploaded|sent)|pending|draft|awaiting|"
    r"cancell?ed|failed|rejected|on\s+hold|revision\s+required|"
    r"reminder|requested)\b", re.I
)


def downstream_evidence(subject):
    """Only affirmative final report or statement *notices* in original subjects.

    An isolated body mention, draft, reminder, or statement of work is not an
    issued deliverable. Never use a reply/forwarded subject as original proof.
    """
    subject = str(subject or "")
    if DOWNSTREAM_NEGATIVE.search(subject):
        return frozenset()
    found = set()
    if FINAL_REPORT_TITLE.search(subject) and DOWNSTREAM_READY.search(subject):
        found.add("FINAL_REPORT")
    # Statement of Work (SOW) is unrelated to an issued billing Statement.
    if (STATEMENT_TITLE.search(subject) and DOWNSTREAM_READY.search(subject)
            and not re.search(r"\bstatement\s+of\s+work\b", subject, re.I)):
        found.add("STATEMENT")
    return frozenset(found)



def unique_project(subject):
    """Unique AMEA is authoritative; otherwise require one unambiguous ID."""
    text = str(subject or "")
    amea = {s.upper() for s in AMEA.findall(text)}
    if len(amea) == 1:
        return next(iter(amea))
    if len(amea) > 1:
        return None
    candidates = {s.upper() for s in X_PROJECT.findall(text)}
    candidates.update(s.upper() for s in H_PROJECT.findall(text))
    return next(iter(candidates)) if len(candidates) == 1 else None


def exact_sender(row, expected):
    actual = email_set(plain_field(row.get("From")))
    return actual == {expected}


def parse_time(value):
    try:
        d = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if d.tzinfo is None:
            return None
        return d.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def event(row, source):
    key = plain_field(row.get("Mail Key")).strip()
    if not key or key == SMOKE_KEY or not exact_sender(row, source):
        return None
    if plain_field(row.get("Direction")) != "INBOUND":
        return None
    stamp_text = plain_field(row.get("Received At"))
    if not since_2026(stamp_text):
        return None
    date = parse_time(stamp_text)
    subject = plain_field(row.get("Subject")).strip()
    if not date or not subject or REPLY.match(subject) or plain_field(row.get("In Reply To")).strip():
        return None
    project = unique_project(subject)  # Quoted body IDs are NOT an identity proof.
    if not project:
        return None
    contract = bool(CONTRACT_CREATED.search(subject) and not CONTRACT_NEGATIVE.search(subject))
    po_state = document_evidence(subject, "", "PO", False)
    if po_state not in ("RECEIVED_NOTICE", "CONFIRMED_NOTICE", "NOT_RECEIVED_NOTICE", "ACTION_REQUESTED"):
        po_state = None
    downstream = downstream_evidence(subject)
    if not contract and not po_state and not downstream:
        return None
    return dict(project=project, at=date, contract=contract, po=po_state,
                downstream=downstream,
                source="CRM" if source == CRM_SENDER else "CSS", key=key)


def choose_state(contract, po_events):
    """Only a verified event of receipt/approval removes a project from PO_REQUIRED."""
    if not po_events:
        return "PO_REQUIRED", None, "REQUEST_PO"
    recent = max(e["at"] for e in po_events)
    latest = [e for e in po_events if e["at"] == recent]
    states = {e["po"] for e in latest}
    if len(states) != 1:
        return "PO_REVIEW", None, "REVIEW_PO_CONFLICT"
    latest_event = sorted(latest, key=lambda e: (e["source"], e["key"]))[0]
    state = next(iter(states))
    if state == "CONFIRMED_NOTICE":
        return "PO_CONFIRMED_NOTICE", latest_event, "VERIFY_PO_FILE"
    if state == "RECEIVED_NOTICE":
        return "PO_RECEIVED_NOTICE", latest_event, "VERIFY_PO_FILE"
    return "PO_REQUIRED", latest_event, "REQUEST_PO"


def build_tracker(events, at_utc):
    grouped = defaultdict(lambda: {"contracts": [], "po": [], "downstream": []})
    for e in events:
        g = grouped[e["project"]]
        if e["contract"]:
            g["contracts"].append(e)
        if e["po"]:
            g["po"].append(e)
        if e.get("downstream"):
            g["downstream"].append(e)
    rows = []
    for project, group in sorted(grouped.items()):
        if not group["contracts"]:
            continue  # Contract absence is NOT a missing PO.
        contract = sorted(group["contracts"], key=lambda e: (e["at"], e["key"]))[0]
        state, po, action = choose_state(contract, group["po"])
        # Final report / statement is a downstream process milestone. Require
        # original notice timestamp STRICTLY after the Contract creation.
        milestones = [e for e in group["downstream"] if e["at"] > contract["at"]]
        latest = max(milestones, key=lambda e: (e["at"], e["key"])) if milestones else None
        evidence_types = set().union(*(e["downstream"] for e in milestones))
        evidence_type = "_AND_".join(sorted(evidence_types)) if evidence_types else ""
        contradictory = latest is not None and any(
            e["at"] > latest["at"] and e["po"] in ("ACTION_REQUESTED", "NOT_RECEIVED_NOTICE")
            for e in group["po"]
        )
        inference = ("CONFLICT_REVIEW" if contradictory else
                     "ASSUMED_BY_DOWNSTREAM_NOTICE" if latest else "NOT_OBSERVED")
        rows.append({
            "Project ID": project,
            "PO Status": state,
            "Contract Notice UTC": contract["at"].isoformat(),
            "Contract Source": contract["source"],
            "Contract Mail Key": contract["key"],
            "Last PO Notice UTC": po["at"].isoformat() if po else "",
            "PO Notice Source": po["source"] if po else "",
            "PO Mail Key": po["key"] if po else "",
            "Next Action": action,
            "Evidence Rule": "ORIGINAL_EXACT_SENDER_SUBJECT_V2_DOWNSTREAM_AFTER_CONTRACT",
            "Last Sync UTC": at_utc,
            "Downstream Evidence Type": evidence_type,
            "Downstream Evidence UTC": latest["at"].isoformat() if latest else "",
            "Downstream Source": latest["source"] if latest else "",
            "Downstream Mail Key": latest["key"] if latest else "",
            "Submission Inference": inference,
        })
    return rows


def manual_file_verified(previous):
    """User-entered attestation, never inferred from a mail subject alone.

    Requires explicit verification, a traceable document reference, a named
    reviewer, and a timestamp with timezone; incomplete claims stay on queue.
    """
    if plain_field(previous.get("PO Document Verification")).strip() != "FILE_VERIFIED":
        return False
    if not plain_field(previous.get("PO Document Reference")).strip():
        return False
    if not plain_field(previous.get("PO Verified By")).strip():
        return False
    return parse_time(plain_field(previous.get("PO Verified At"))) is not None


def apply_followup(rows, indexed):
    for fields in rows:
        previous = (indexed.get(fields["Project ID"]) or {}).get("fields") or {}
        if manual_file_verified(previous):
            fields["PO Followup Queue"] = "FILE_VERIFIED_ATTESTED"
            fields["Next Action"] = "NO_PO_FOLLOWUP_MANUAL_FILE_ATTESTED"
        elif fields["PO Status"] in ("PO_RECEIVED_NOTICE", "PO_CONFIRMED_NOTICE"):
            fields["PO Followup Queue"] = "PO_FILE_REVIEW"
            fields["Next Action"] = "VERIFY_PO_FILE"
        elif fields.get("Submission Inference") == "ASSUMED_BY_DOWNSTREAM_NOTICE":
            fields["PO Followup Queue"] = "PO_SUBMITTED_INFERRED"
            fields["Next Action"] = "NO_PO_REQUEST_FINAL_REPORT_OR_STATEMENT"
        elif fields.get("Submission Inference") == "CONFLICT_REVIEW":
            fields["PO Followup Queue"] = "PO_EVIDENCE_CONFLICT_REVIEW"
            fields["Next Action"] = "REVIEW_CONTRADICTORY_PO_NOTICE"
        elif fields["PO Status"] == "PO_REQUIRED":
            fields["PO Followup Queue"] = "PO_REQUIRED"
            fields["Next Action"] = "REQUEST_PO"
        else:
            fields["PO Followup Queue"] = "PO_FILE_REVIEW"
            fields["Next Action"] = "VERIFY_PO_FILE"


def find_source(token, root, tables, name):
    matches = [x for x in tables if x.get("name") == name]
    if len(matches) != 1:
        raise SafeError("CONTRACT_PO_SOURCE_TABLE_MISSING_OR_DUPLICATE_" + name.replace(" ", "_"))
    return root + "/tables/" + urllib.parse.quote(matches[0]["table_id"], safe="")


def load_events(token, root):
    tables = list_all(root + "/tables", token, "contract_po_tables")
    events = []
    counts = Counter()
    for name, source in SOURCES:
        path = find_source(token, root, tables, name)
        for record in list_all(path + "/records", token, "contract_po_source"):
            f = record.get("fields") or {}
            # The CRM source must retain exact collector namespace to be trusted.
            if name == "CRM Filtered Mail Intake" and (
                plain_field(f.get("Source Account")) != CRM_ACCOUNT
                or plain_field(f.get("Source Filter")) != "EXACT_FROM_CRM"):
                continue
            item = event(f, source)
            if item:
                events.append(item)
                counts["contract"] += int(item["contract"])
                counts["po_notice"] += int(bool(item["po"]))
                counts["downstream_mail_notices"] += int(bool(item.get("downstream")))
    return events, counts, tables


def ensure_tracker(token, root, tables):
    matches = [t for t in tables if t.get("name") == TABLE]
    if len(matches) > 1:
        raise SafeError("CONTRACT_PO_DUPLICATE_TRACKER")
    tid = matches[0]["table_id"] if matches else None
    if not tid:
        result = api("POST", root + "/tables", token,
                     data={"table": {
                         "name": TABLE, "default_view_name": "전체 Contract PO",
                         "fields": [{"field_name": name, "type": 1} for name in FIELDS],
                     }}, action="contract_po_create_table")
        tid = (result.get("table") or {}).get("table_id") or result.get("table_id")
    if not tid:
        raise SafeError("CONTRACT_PO_CREATE_UNVERIFIED")
    path = root + "/tables/" + urllib.parse.quote(tid, safe="")
    fields = {f.get("field_name"): f for f in get_fields(token, path)}
    for name in FIELDS:
        if name not in fields:
            api("POST", path + "/fields", token,
                data={"field_name": name, "type": 1},
                action="contract_po_create_field")
    fields = {f.get("field_name"): f for f in get_fields(token, path)}
    if any(fields.get(k, {}).get("type") != 1 for k in FIELDS):
        raise SafeError("CONTRACT_PO_SCHEMA_INVALID")
    return tid, path, fields


def ensure_pending_view(token, path, field_id):
    """A strictly verified filtered view; never label an unfiltered view 'PO 수령 필요'."""
    import json
    views = list_views(token, path)
    label, temp = "PO 수령 필요", "설정중_PO 수령 필요"
    view_id = views.get(label) or views.get(temp)
    if not view_id:
        payload = api("POST", path + "/views", token,
                      data={"view_name": temp, "view_type": "grid"},
                      action="contract_po_view_create")
        view_id = (payload.get("view") or {}).get("view_id")
        if not view_id:
            view_id = list_views(token, path).get(temp)
    if not view_id:
        raise SafeError("CONTRACT_PO_VIEW_ID_MISSING")
    endpoint = path + "/views/" + urllib.parse.quote(view_id, safe="")
    rule = {"conjunction": "and", "conditions": [{
        "field_id": field_id, "operator": "is", "value": json.dumps(["PO_REQUIRED"])
    }]}
    api("PATCH", endpoint, token,
        data={"view_name": label, "property": {"filter_info": rule}},
        action="contract_po_view_filter")
    fetched = api("GET", endpoint, token, action="contract_po_view_verify").get("view") or {}
    info = (fetched.get("property") or {}).get("filter_info") or {}
    conditions = info.get("conditions") or []
    if (fetched.get("view_name") != label or info.get("conjunction") != "and"
            or len(conditions) != 1 or conditions[0].get("field_id") != field_id
            or conditions[0].get("operator") != "is"
            or json.loads(conditions[0].get("value") or "null") != ["PO_REQUIRED"]):
        raise SafeError("CONTRACT_PO_VIEW_NOT_VERIFIED")
    return view_id


def sync(token, path, desired):
    existing = list_all(path + "/records", token, "contract_po_existing")
    indexed = {}
    for record in existing:
        key = plain_field((record.get("fields") or {}).get("Project ID")).strip()
        if key in indexed:
            raise SafeError("CONTRACT_PO_DUPLICATE_PROJECT")
        if key:
            indexed[key] = record
    # Preserve user-edited manual evidence fields (never auto-write them).
    # Only the derived queue and next action may depend on attestations.
    apply_followup(desired, indexed)
    creates, updates = [], []
    for fields in desired:
        key = fields["Project ID"]
        old = indexed.get(key)
        if not old:
            creates.append({"fields": fields})
        elif any(plain_field((old.get("fields") or {}).get(k)) != str(v)
                 for k, v in fields.items() if k != "Last Sync UTC"):
            updates.append({"record_id": old["record_id"], "fields": fields})
    for operation, batches in (("batch_create", creates), ("batch_update", updates)):
        for offset in range(0, len(batches), 25):
            chunk = batches[offset:offset + 25]
            outcome = api("POST", path + "/records/" + operation, token,
                          data={"records": chunk}, action="contract_po_" + operation)
            if len(outcome.get("records") or []) != len(chunk):
                raise SafeError("CONTRACT_PO_WRITE_UNVERIFIED")
    # No destructive delete: a partial 2026 mail scan must not erase history.
    refreshed = list_all(path + "/records", token, "contract_po_readback")
    lookup = {plain_field((r.get("fields") or {}).get("Project ID")).strip(): r for r in refreshed}
    for fields in desired:
        actual = (lookup.get(fields["Project ID"]) or {}).get("fields") or {}
        if any(plain_field(actual.get(k)) != str(v) for k, v in fields.items()
               if k != "Last Sync UTC"):
            raise SafeError("CONTRACT_PO_READBACK_MISMATCH")
    return len(creates), len(updates), len(desired)


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("CONTRACT_PO_WRONG_BASE")
    token, root = auth()
    events, counts, tables = load_events(token, root)
    now = datetime.now(timezone.utc).isoformat()
    desired = build_tracker(events, now)
    tid, path, fields = ensure_tracker(token, root, tables)
    created, updated, total = sync(token, path, desired)
    vid = ensure_pending_view(token, path, fields["PO Followup Queue"]["field_id"])
    pending = sum(x["PO Followup Queue"] == "PO_REQUIRED" for x in desired)
    manually_attested = sum(x["PO Followup Queue"] == "FILE_VERIFIED_ATTESTED" for x in desired)
    needs_file_review = sum(x["PO Followup Queue"] == "PO_FILE_REVIEW" for x in desired)
    inferred = sum(x["PO Followup Queue"] == "PO_SUBMITTED_INFERRED" for x in desired)
    conflicting = sum(x["PO Followup Queue"] == "PO_EVIDENCE_CONFLICT_REVIEW" for x in desired)
    report_evidence = sum("FINAL_REPORT" in x["Downstream Evidence Type"] for x in desired)
    statement_evidence = sum("STATEMENT" in x["Downstream Evidence Type"] for x in desired)
    print("CONTRACT_PO_TRACKER_PASS contract_notices=" + str(counts["contract"]) +
          " po_notices=" + str(counts["po_notice"]) + " projects=" + str(total) +
          " po_required=" + str(pending) + " manual_file_attested=" + str(manually_attested) +
          " po_file_review=" + str(needs_file_review) +
          " downstream_notice_mails=" + str(counts["downstream_mail_notices"]) +
          " final_report_projects=" + str(report_evidence) +
          " statement_projects=" + str(statement_evidence) +
          " inferred_po_submitted_projects=" + str(inferred) +
          " po_evidence_conflict_review=" + str(conflicting) +
          " created=" + str(created) + " updated=" + str(updated) +
          " source_mail_writes=0")
    print("CONTRACT_PO_PENDING_VIEW=" + BASE_URL + "?table=" + tid + "&view=" + vid)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("CONTRACT_PO_TRACKER_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
