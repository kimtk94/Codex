#!/usr/bin/env python3
"""Pure seven-case QQ invoice replay protocol; NEVER performs a write.

This is a contract for a separately reviewed future stage-only writer, not an
implementation of that writer. GitHub concurrency/GET-then-PUT are not atomic
CAS, and a JSON approval record is not proof of the approver's identity.
Never log raw rows, fingerprints, IDs or approval payloads.
"""
import datetime as dt
import hashlib
import json
import re
from collections import Counter

if __package__:
    from .qq_precursor_prewrite_gate import verify_staged_readback
else:
    from qq_precursor_prewrite_gate import verify_staged_readback

STAGE = "QQ 2026 Invoice Backfill"
REASONS = (
    "SOURCE_UNVERIFIED", "CURSOR_CHANGED", "SNAPSHOT_CHANGED",
    "SINK_ALREADY_PRESENT",
    "APPROVAL_ABSENT", "APPROVAL_SCOPE_INVALID", "APPROVAL_BINDING_INVALID",
    "APPROVAL_EXPIRED", "APPROVAL_UNTRUSTED",
    "SERIALIZATION_UNPROVEN", "ATOMIC_COMMIT_UNPROVEN",
)
DIGITS = re.compile(r"[0-9]{10,15}\Z")


def _fingerprint(row):
    """Private process-only digest. Not safe for public logs or receipts."""
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).digest()


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def evaluate_case(case, approval, before, after, proof_ok, now):
    """Return an allowlisted HOLD reason; never an authorization to write.

    Approval is only a candidate for future independently verified approval:
    approval_verified cannot be inferred from record fields, usernames or PR
    merge. Even a matching, non-expired approval does not create CAS or lock.
    """
    key = str(case.get("invoice_number") or "").strip()
    if not DIGITS.fullmatch(key) or not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise ValueError("REPLAY_SCOPE_OR_CLOCK_INVALID")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("REPLAY_SNAPSHOT_SHAPE_INVALID")
    if not proof_ok:
        return "SOURCE_UNVERIFIED"
    if before.get("cursor") != after.get("cursor"):
        return "CURSOR_CHANGED"
    if before.get("audit") != after.get("audit"):
        return "CURSOR_CHANGED"
    if any(str(row.get("invoice_number") or "") == key
           for tab in ("qq", "css") for row in after.get(tab, [])):
        return "SINK_ALREADY_PRESENT"
    if any(before.get(t) != after.get(t) for t in ("qq", "css", "extract")):
        return "SNAPSHOT_CHANGED"
    if approval is None:
        return "APPROVAL_ABSENT"
    if not isinstance(approval, dict) or approval.get("decision") != "APPROVED":
        return "APPROVAL_SCOPE_INVALID"
    if approval.get("scope") != "QQ_STAGE_ONLY" or approval.get("tab") != STAGE:
        return "APPROVAL_SCOPE_INVALID"
    # Match all source identity fields, explicit amount, one case nonce and
    # private evidence digest. A bare invoice number is never sufficient.
    required = ("invoice_number", "amount_krw", "imap_folder", "imap_uid",
                "uidvalidity", "evidence")
    if any(not isinstance(case.get(f), str) or not case[f] for f in required):
        return "SOURCE_UNVERIFIED"
    if case["imap_folder"] != "INBOX":
        return "SOURCE_UNVERIFIED"
    inbox = [x for x in after.get("cursor", [])
             if str(x.get("year")) == "2026"
             and str(x.get("folder") or "").upper() == "INBOX"]
    if len(inbox) != 1 or str(inbox[0].get("uidvalidity") or "") != case["uidvalidity"]:
        return "SOURCE_UNVERIFIED"
    bindings = ("invoice_number", "amount_krw", "imap_folder", "imap_uid",
                "uidvalidity")
    if any(str(approval.get(f) or "") != case[f] for f in bindings):
        return "APPROVAL_BINDING_INVALID"
    # The evidence hash is binary and must stay in private memory. No raw
    # digest or invoice identifier is published in CI status.
    if approval.get("evidence_digest") != _fingerprint(
            {k: case[k] for k in required}):
        return "APPROVAL_BINDING_INVALID"
    if not isinstance(approval.get("nonce"), str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{16,128}", approval["nonce"]):
        return "APPROVAL_BINDING_INVALID"
    approved_at = _utc(approval.get("approved_at"))
    expires_at = _utc(approval.get("expires_at"))
    now = now.astimezone(dt.timezone.utc)
    if (approved_at is None or expires_at is None or approved_at > now
            or expires_at <= now or expires_at <= approved_at):
        return "APPROVAL_EXPIRED"
    # Never trust an unverified approval claim. A future implementation needs
    # an independent authenticated approver + immutable receipt provenance.
    # Even an assertion like _authenticated_approval_proof=True in JSON is
    # untrusted. An independent verifier must be implemented and reviewed
    # in a future PR before any writer could use authenticated permissions.
    # This module accepts no authority-bearing input or locking claim.
    return "APPROVAL_UNTRUSTED"


def plan_cases(cases, approvals, before, after, proofs, now):
    """Private per-case reasoning, public integer counts only, always HOLD."""
    if not isinstance(cases, list) or not 1 <= len(cases) <= 7:
        raise ValueError("REPLAY_CASE_COUNT_INVALID")
    keys = [str(case.get("invoice_number") or "") for case in cases]
    if len(keys) != len(set(keys)) or any(not DIGITS.fullmatch(k) for k in keys):
        raise ValueError("REPLAY_DUPLICATE_OR_INVALID_CASE")
    if not isinstance(approvals, dict) or not isinstance(proofs, dict):
        raise ValueError("REPLAY_INPUT_MAP_INVALID")
    if set(proofs) != set(keys) or set(approvals) - set(keys):
        raise ValueError("REPLAY_PROOF_OR_APPROVAL_SCOPE_INVALID")
    used_nonces=set()
    for a in approvals.values():
        if isinstance(a, dict) and isinstance(a.get("nonce"), str):
            nonce=a["nonce"]
            if nonce in used_nonces:
                raise ValueError("REPLAY_APPROVAL_NONCE_REUSED")
            used_nonces.add(nonce)
    counts=Counter({r:0 for r in REASONS})
    for case in cases:
        code=evaluate_case(case, approvals.get(case["invoice_number"]),
                           before, after, proofs[case["invoice_number"]], now)
        counts[code]+=1
    result={
        "replay_protocol_cases":len(cases),
        "replay_protocol_holds":len(cases),
        "replay_protocol_approval_required":len(cases),
        "replay_protocol_authenticated_approvals":0,
        "replay_protocol_writer_exclusion_verified":0,
        "replay_protocol_atomic_cas_verified":0,
        "replay_protocol_stage_writes":0,
        "replay_protocol_cursor_writes":0,
        "replay_protocol_canonical_writes":0,
        "replay_protocol_status":"HOLD",
    }
    result.update({"replay_protocol_"+k.lower():counts[k] for k in REASONS})
    return result


def reconcile_uncertain_attempt(expected, stage_rows, cursor_before, cursor_after,
                                receipt_claim=None):
    """Future crash-after-append simulation. Never retry or persist here."""
    if cursor_before != cursor_after:
        return "CURSOR_CHANGED_HOLD"
    invoice=str(expected.get("invoice_number") or "")
    if not DIGITS.fullmatch(invoice):
        return "INVALID_ID_HOLD"
    matching=[row for row in stage_rows if row.get("invoice_number")==invoice]
    if len(matching)>1:
        return "DUPLICATE_HOLD"
    if not matching:
        return "ABSENT_RETRY_REQUIRES_NEW_REVIEW"
    if not verify_staged_readback(expected, matching, cursor_before, cursor_after):
        return "CONFLICT_HOLD"
    # The row matches an expected write, but it is not proof that the save
    # happened under an authenticated, durable, independent approval/receipt.
    # Even a caller-controlled "VERIFIED" field must not authorize a retry.
    if receipt_claim is not None:
        return "CLAIMED_RECEIPT_UNAUTHENTICATED_HOLD"
    return "EXACT_ROW_PRESENT_RECEIPT_UNVERIFIED_HOLD"
