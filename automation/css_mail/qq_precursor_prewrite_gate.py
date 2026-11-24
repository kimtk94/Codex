#!/usr/bin/env python3
"""Immutable in-memory readback checks for historical QQ staging recovery.

This module NEVER executes a writer or grants approval. Google Sheets GET
followed by PUT is not an atomic CAS; a stable snapshot is informational only.
Identifiers/hashes remain in process memory, never in public artifacts.
"""
import datetime as dt
import hashlib
import json
import re
from collections import Counter

TABS=("qq","css","extract","cursor","audit")
DRIFT_LABELS={
    "qq":"QQ_STAGING_DRIFT", "css":"CANONICAL_DRIFT",
    "extract":"EXTRACT_DRIFT", "cursor":"CURSOR_DRIFT", "audit":"AUDIT_DRIFT",
}

def fingerprint(rows):
    """Canonical in-memory snapshot hash; MUST NOT be logged or exported."""
    if not isinstance(rows,list) or any(not isinstance(x,dict) for x in rows):
        raise ValueError("REPLAY_SNAPSHOT_SHAPE_INVALID")
    normalized=sorted(json.dumps(row,sort_keys=True,ensure_ascii=False,
                                  separators=(",",":")) for row in rows)
    return hashlib.sha256(json.dumps(normalized,ensure_ascii=False,
                                     separators=(",",":")).encode("utf-8")).digest()

def indexed(rows,label):
    by_number={}
    for row in rows:
        number=str(row.get("invoice_number") or "").strip()
        if not number:
            continue
        if not re.fullmatch(r"[0-9]{10,15}",number):
            raise ValueError("REPLAY_"+label+"_IDENTIFIER_INVALID")
        if number in by_number:
            raise ValueError("REPLAY_"+label+"_DUPLICATE")
        by_number[number]=row
    return by_number

def prewrite_readback(before,after,targets):
    """Verify two full read-only snapshots and seven private source records.

    Even if all checks pass, NO write is eligible without atomicity design,
    explicit case approval, authoritative source receipt and post-save readback.
    """
    numbers=[str(t.get("number") or "").strip() for t in targets
             if t.get("category")=="PRE_CURSOR_MISSING"]
    if len(numbers)>35 or len(set(numbers))!=len(numbers):
        raise ValueError("REPLAY_SCOPE_OR_DUPLICATE_INVALID")
    for snapshots in (before,after):
        if set(snapshots)!=set(TABS):
            raise ValueError("REPLAY_SNAPSHOT_INCOMPLETE")
    drift={name:fingerprint(before[name])!=fingerprint(after[name])
           for name in TABS}
    # Only the second snapshot can describe current staging; any drift of
    # source, cursor, audit, or a sink is a fail-closed global HOLD.
    check=indexed(after["qq"],"QQ")
    canonical=indexed(after["css"],"CSS")
    extracts=indexed(after["extract"],"EXTRACT")
    before_extract=indexed(before["extract"],"EXTRACT")
    reasons=Counter()
    for t in targets:
        if t.get("category")!="PRE_CURSOR_MISSING":
            continue
        number=t["number"]
        if number in check or number in canonical:
            reasons["EXISTING_SINK_RECORD"]+=1
        elif number not in extracts or number not in before_extract:
            reasons["EXTRACT_MISSING"]+=1
        elif extracts[number]!=before_extract[number] or extracts[number]!=t.get("extract"):
            reasons["EXTRACT_TARGET_MISMATCH"]+=1
        else:
            reasons["STABLE_SOURCE_CANDIDATE"]+=1
    unstable=any(drift.values())
    stable_count=reasons["STABLE_SOURCE_CANDIDATE"] if not unstable else 0
    result={
        "replay_prewrite_target_count":len(numbers),
        "replay_prewrite_stable_readback_count":stable_count,
        "replay_prewrite_snapshot_changed":int(unstable),
        "replay_prewrite_approval_required":len(numbers),
        "replay_prewrite_atomic_cas_verified":0,
        "replay_prewrite_write_authorized":0,
        "replay_postwrite_verified":0,
        "replay_prewrite_status":"HOLD",
    }
    result.update({"replay_prewrite_"+DRIFT_LABELS[n].lower():int(drift[n])
                   for n in TABS})
    result.update({"replay_prewrite_"+n.lower():reasons[n] for n in
                   ("EXISTING_SINK_RECORD","EXTRACT_MISSING",
                    "EXTRACT_TARGET_MISMATCH")})
    return result

def verify_staged_readback(expected,staging_rows,cursor_before,cursor_after):
    """Future post-save contract; pure simulation/test only, no API writes."""
    if fingerprint(cursor_before)!=fingerprint(cursor_after):
        return False
    inv=str(expected.get("invoice_number") or "")
    if not re.fullmatch(r"[0-9]{10,15}",inv):
        return False
    matches=[r for r in staging_rows
             if str(r.get("invoice_number") or "")==inv]
    if len(matches)!=1:
        return False
    actual=matches[0]
    keys=("invoice_number","issued_month","amount_krw","amea_project_id",
          "h_project_id","po_reference","imap_folder","imap_uid",
          "filename","evidence","backfill_utc")
    # This checks the *future persisted row*, not the pre-write plan.
    # A missing or fabricated execution timestamp must not be accepted as
    # evidence of a durable post-save result. Only an explicitly supplied
    # timezone-aware backfill_utc in the expected written payload qualifies.
    ts=expected.get("backfill_utc")
    if not isinstance(ts,str) or not ts:
        return False
    try:
        parsed=dt.datetime.fromisoformat(ts.replace("Z","+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    # Non-authoritative IMAP arrival dates cannot invent issue months.
    if expected.get("issued_month") not in (None,""):
        return False
    if any(str(actual.get(k,""))!=str(expected.get(k,"")) for k in keys):
        return False
    return str(actual.get("issued_month") or "")==""
