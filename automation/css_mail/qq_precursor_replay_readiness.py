#!/usr/bin/env python3
"""Pure QQ pre-cursor invoice replay triage. No writes, cursor changes or PII output."""
from collections import Counter
import re

REASONS = (
    "AMOUNT_CONFLICT", "EXISTING_SINK_RECORD", "INVALID_EXTRACT_ID_OR_AMOUNT",
    "ORIGINAL_SEARCH_ABSENT", "INGEST_EVIDENCE_MISSING",
    "INGEST_UID_OR_EPOCH_CONFLICT", "ORIGINAL_HEADER_UNVERIFIED",
    "MIME_IDENTITY_OR_AMOUNT_UNVERIFIED", "EVIDENCE_VERIFIED_HOLD",
)

def _amount(row):
    raw = str((row or {}).get("amount_krw") or "").strip()
    return int(raw) if re.fullmatch(r"[0-9]+", raw) and int(raw)>0 else None

def classify_precursor(target, evidence):
    """Classify a single source privately. Every return means NO WRITE."""
    if target.get("category") != "PRE_CURSOR_MISSING":
        raise ValueError("REPLAY_SCOPE_INVALID")
    extract=target.get("extract") or {}
    invoice=str(target.get("number") or "").strip()
    if (not re.fullmatch(r"[0-9]{10,15}", invoice)
            or str(extract.get("invoice_number") or "").strip()!=invoice
            or _amount(extract) is None):
        return "INVALID_EXTRACT_ID_OR_AMOUNT"
    for sink in ("qq","css"):
        existing=target.get(sink)
        if existing is not None:
            a=_amount(existing)
            if a is not None and a!=_amount(extract):
                return "AMOUNT_CONFLICT"
            return "EXISTING_SINK_RECORD"
    checks=(
        ("search_matched","ORIGINAL_SEARCH_ABSENT"),
        ("ingest_present","INGEST_EVIDENCE_MISSING"),
        ("ingest_epoch_matched","INGEST_UID_OR_EPOCH_CONFLICT"),
        ("header_verified","ORIGINAL_HEADER_UNVERIFIED"),
        ("mime_verified","MIME_IDENTITY_OR_AMOUNT_UNVERIFIED"),
    )
    for field,reason in checks:
        if not evidence.get(field):
            return reason
    return "EVIDENCE_VERIFIED_HOLD"

def summarize_replay(targets, evidence_by_invoice):
    """Aggregate per-invoice verdicts without publishing identifiers or amounts."""
    subset=[t for t in targets if t.get("category")=="PRE_CURSOR_MISSING"]
    ids=[t.get("number") for t in subset]
    if len(subset)>35 or len(ids)!=len(set(ids)):
        raise ValueError("REPLAY_DUPLICATE_OR_UNBOUNDED_TARGET")
    if set(ids)!=set(evidence_by_invoice):
        raise ValueError("REPLAY_PROOF_COVERAGE_INCOMPLETE")
    counts=Counter({key:0 for key in REASONS})
    for target in subset:
        counts[classify_precursor(target,evidence_by_invoice[target["number"]])]+=1
    result={
        "replay_precursor_target_count":len(subset),
        "replay_source_proved_hold":counts["EVIDENCE_VERIFIED_HOLD"],
        "replay_stage_writes_approved":0,
        "replay_canonical_writes_approved":0,
        "replay_official_issue_date_proved":0,
        "replay_persisted_receipts":0,
        "replay_current_sink_readback_proved":0,
    }
    result.update({"replay_reason_"+k.lower():counts[k] for k in REASONS})
    return result
