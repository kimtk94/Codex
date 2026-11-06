#!/usr/bin/env python3
"""Project-level SIF notice tracker from original, exact-sender CSS/CRM mail.

Source notices only: APPROVED_NOTICE does not prove a signed or physically
received SIF file. No original mail, SFDC, billing, or existing SIF table edits.
SIF evidence is tracked before and after Contract; PO remains Contract-gated.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
import sys
import urllib.parse

import contract_po_tracker as po
from jiin_crm_sif_po_audit import evidence
from qq_mail_ingest import SafeError, SMOKE_KEY, api, auth, get_fields, list_all, plain_field
from mail_classification_2026 import since_2026
from setup_sales_web import EXPECTED_BASE, BASE_URL, list_views

TABLE = "SIF Evidence Tracker"
FIELDS = (
    "Project ID", "Contract Notice", "SIF Status", "SIF Followup Queue",
    "SIF Notice UTC", "SIF Source", "SIF Mail Key", "Next Action",
    "Evidence Rule", "Last Sync UTC",
)
STATUS_ACTION = {
    "NOT_OBSERVED": ("SIF_NOT_OBSERVED", "CHECK_SIF_WITH_OWNER"),
    "MENTION_ONLY": ("SIF_MENTION_ONLY", "REVIEW_SIF_NOTICE"),
    "ACTION_REQUESTED": ("SIF_REQUESTED", "REQUEST_SIF"),
    "SUBMITTED_NOTICE": ("SIF_SUBMITTED_NOTICE", "VERIFY_SIF_RECEIPT"),
    "RECEIVED_NOTICE": ("SIF_RECEIVED_NOTICE", "VERIFY_SIF_FILE"),
    "APPROVED_NOTICE": ("SIF_APPROVED_NOTICE", "VERIFY_APPROVAL_AND_SIF_FILE"),
    "REJECTED_NOTICE": ("SIF_REJECTED_NOTICE", "FOLLOW_UP_SIF_CORRECTION"),
}


def sif_event(fields, sender):
    key = plain_field(fields.get("Mail Key")).strip()
    if not key or key == SMOKE_KEY or not po.exact_sender(fields, sender):
        return None
    if plain_field(fields.get("Direction")) != "INBOUND":
        return None
    received = plain_field(fields.get("Received At"))
    if not since_2026(received):
        return None
    when = po.parse_time(received)
    subject = plain_field(fields.get("Subject")).strip()
    if not when or not subject or po.REPLY.match(subject) or plain_field(fields.get("In Reply To")).strip():
        return None
    state = evidence(subject, "", "SIF")
    if state == "NOT_OBSERVED":
        return None
    project = po.unique_project(subject)
    if not project:
        return dict(project=None, at=when, state=state,
                    source="CRM" if sender == po.CRM_SENDER else "CSS", key=key)
    return dict(project=project, at=when, state=state,
                source="CRM" if sender == po.CRM_SENDER else "CSS", key=key)


def latest_sif(events):
    """More recent explicit notices supersede earlier ones, except contradictions."""
    if not events:
        return "SIF_NOT_OBSERVED", None, "CHECK_SIF_WITH_OWNER"
    specific = [e for e in events if e["state"] != "MENTION_ONLY"]
    pool = specific or events
    latest = max(e["at"] for e in pool)
    tied = [e for e in pool if e["at"] == latest]
    states = {e["state"] for e in tied}
    if len(states) > 1:
        return "SIF_REVIEW", None, "REVIEW_CONFLICTING_SIF_NOTICES"
    chosen = sorted(tied, key=lambda e: (e["source"], e["key"]))[0]
    state = next(iter(states))
    # After a previous explicit approval, a new request/rejection is ambiguous
    # (new sample, replacement SIF, different project version).
    if state in ("ACTION_REQUESTED", "REJECTED_NOTICE") and any(
        e["state"] == "APPROVED_NOTICE" and e["at"] < latest for e in specific
    ):
        return "SIF_REVIEW", chosen, "REVIEW_POST_APPROVAL_SIF_NOTICE"
    status, action = STATUS_ACTION[state]
    return status, chosen, action


def build_rows(contract_events, sif_events, timestamp):
    contracts = defaultdict(list)
    sifs = defaultdict(list)
    for e in contract_events:
        if e["contract"]:
            contracts[e["project"]].append(e)
    for e in sif_events:
        if e["project"]:
            sifs[e["project"]].append(e)
    rows = []
    for project in sorted(set(contracts) | set(sifs)):
        status, chosen, action = latest_sif(sifs[project])
        rows.append({
            "Project ID": project,
            "Contract Notice": "YES" if contracts[project] else "NO",
            "SIF Status": status,
            "SIF Followup Queue": "APPROVAL_NOTICE_OBSERVED" if status == "SIF_APPROVED_NOTICE" else "REVIEW_REQUIRED",
            "SIF Notice UTC": chosen["at"].isoformat() if chosen else "",
            "SIF Source": chosen["source"] if chosen else "",
            "SIF Mail Key": chosen["key"] if chosen else "",
            "Next Action": action,
            "Evidence Rule": "EXACT_SENDER_ORIGINAL_SUBJECT_ONLY_V1",
            "Last Sync UTC": timestamp,
        })
    return rows


def load_sources(token, root):
    tables = list_all(root + "/tables", token, "sif_tables")
    contracts = []
    sifs = []
    counts = Counter()
    for name, sender in po.SOURCES:
        path = po.find_source(token, root, tables, name)
        for record in list_all(path + "/records", token, "sif_source"):
            f = record.get("fields") or {}
            if name == "CRM Filtered Mail Intake" and (
                plain_field(f.get("Source Account")) != po.CRM_ACCOUNT or
                plain_field(f.get("Source Filter")) != "EXACT_FROM_CRM"
            ):
                continue
            c = po.event(f, sender)
            if c and c["contract"]:
                contracts.append(c)
            e = sif_event(f, sender)
            if e:
                counts["sif_notices"] += 1
                if e["project"]:
                    sifs.append(e)
                else:
                    counts["sif_notices_without_unique_subject_id"] += 1
    return tables, contracts, sifs, counts


def ensure_table(token, root, tables):
    matches = [t for t in tables if t.get("name") == TABLE]
    if len(matches) > 1:
        raise SafeError("SIF_DUPLICATE_TRACKER_TABLE")
    tid = matches[0]["table_id"] if matches else None
    if not tid:
        data = api("POST", root + "/tables", token, data={"table": {
            "name": TABLE, "default_view_name": "SIF 전체",
            "fields": [{"field_name": name, "type": 1} for name in FIELDS],
        }}, action="sif_tracker_create")
        tid = (data.get("table") or {}).get("table_id") or data.get("table_id")
    if not tid:
        raise SafeError("SIF_TRACKER_TABLE_UNVERIFIED")
    path = root + "/tables/" + urllib.parse.quote(tid, safe="")
    columns = {f.get("field_name"): f for f in get_fields(token, path)}
    for col in FIELDS:
        if col not in columns:
            api("POST", path + "/fields", token, data={"field_name": col, "type": 1},
                action="sif_tracker_add_column")
    columns = {f.get("field_name"): f for f in get_fields(token, path)}
    if any(columns.get(k, {}).get("type") != 1 for k in FIELDS):
        raise SafeError("SIF_TRACKER_SCHEMA_MISMATCH")
    return tid, path, columns


def followup_view(token, path, field_id):
    label, temp = "SIF 승인 확인 필요", "설정중_SIF 승인 확인 필요"
    views = list_views(token, path)
    vid = views.get(label) or views.get(temp)
    if not vid:
        data = api("POST", path + "/views", token,
                   data={"view_name": temp, "view_type": "grid"},
                   action="sif_tracker_view_create")
        vid = (data.get("view") or {}).get("view_id") or list_views(token, path).get(temp)
    if not vid:
        raise SafeError("SIF_TRACKER_VIEW_UNVERIFIED")
    endpoint = path + "/views/" + urllib.parse.quote(vid, safe="")
    rule = {"conjunction": "and", "conditions": [{
        "field_id": field_id, "operator": "is",
        "value": json.dumps(["REVIEW_REQUIRED"]),
    }]}
    api("PATCH", endpoint, token,
        data={"view_name": label, "property": {"filter_info": rule}},
        action="sif_tracker_view_filter")
    view = (api("GET", endpoint, token, action="sif_tracker_view_readback").get("view") or {})
    info = (view.get("property") or {}).get("filter_info") or {}
    cond = info.get("conditions") or []
    if (view.get("view_name") != label or info.get("conjunction") != "and" or
        len(cond) != 1 or cond[0].get("field_id") != field_id or
        cond[0].get("operator") != "is" or
        json.loads(cond[0].get("value") or "null") != ["REVIEW_REQUIRED"]):
        raise SafeError("SIF_TRACKER_FILTER_READBACK_MISMATCH")
    return vid


def sync(token, path, desired):
    existing = list_all(path + "/records", token, "sif_tracker_existing")
    indexed = {}
    for record in existing:
        key = plain_field((record.get("fields") or {}).get("Project ID")).strip()
        if key:
            if key in indexed:
                raise SafeError("SIF_TRACKER_DUPLICATE_PROJECT_ID")
            indexed[key] = record
    creates, updates = [], []
    for fields in desired:
        old = indexed.get(fields["Project ID"])
        if old is None:
            creates.append({"fields": fields})
        elif any(plain_field((old.get("fields") or {}).get(k)) != str(v)
                 for k, v in fields.items() if k != "Last Sync UTC"):
            updates.append({"record_id": old["record_id"], "fields": fields})
    for name, payload in (("batch_create", creates), ("batch_update", updates)):
        for i in range(0, len(payload), 25):
            batch = payload[i:i + 25]
            result = api("POST", path + "/records/" + name, token,
                         data={"records": batch}, action="sif_tracker_" + name)
            if len(result.get("records") or []) != len(batch):
                raise SafeError("SIF_TRACKER_SYNC_UNVERIFIED")
    readback = list_all(path + "/records", token, "sif_tracker_readback")
    verified = {}
    for r in readback:
        key = plain_field((r.get("fields") or {}).get("Project ID")).strip()
        if key in verified:
            raise SafeError("SIF_TRACKER_READBACK_DUPLICATE")
        verified[key] = r.get("fields") or {}
    for fields in desired:
        old = verified.get(fields["Project ID"])
        if old is None or any(plain_field(old.get(k)) != str(v)
                           for k, v in fields.items() if k != "Last Sync UTC"):
            raise SafeError("SIF_TRACKER_READBACK_MISMATCH")
    return len(creates), len(updates)


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("SIF_TRACKER_WRONG_BASE")
    token, root = auth()
    tables, contracts, sifs, counts = load_sources(token, root)
    desired = build_rows(contracts, sifs, datetime.now(timezone.utc).isoformat())
    tid, path, columns = ensure_table(token, root, tables)
    created, updated = sync(token, path, desired)
    view = followup_view(token, path, columns["SIF Followup Queue"]["field_id"])
    pending = sum(r["SIF Followup Queue"] == "REVIEW_REQUIRED" for r in desired)
    approved = sum(r["SIF Status"] == "SIF_APPROVED_NOTICE" for r in desired)
    print("SIF_EVIDENCE_TRACKER_PASS projects=" + str(len(desired)) +
          " contract_projects=" + str(len({x["project"] for x in contracts})) +
          " sif_notices=" + str(counts["sif_notices"]) +
          " without_unique_id=" + str(counts["sif_notices_without_unique_subject_id"]) +
          " approval_notices=" + str(approved) + " followup=" + str(pending) +
          " created=" + str(created) + " updated=" + str(updated) +
          " source_mail_writes=0 existing_sif_monitor_writes=0")
    print("SIF_EVIDENCE_FOLLOWUP_VIEW=" + BASE_URL + "?table=" + tid + "&view=" + view)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("SIF_EVIDENCE_TRACKER_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
