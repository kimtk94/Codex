#!/usr/bin/env python3
"""Local durable *manual Save review* journal; deliberately NO CRM write.

This module is not a Salesforce executor. It can atomically reserve a reviewed
request on the authorized Windows desktop and record manual outcome evidence.
Stale locks and unknown results fail closed; never retry uncertain writes.
Only private files under ~/.sfdc_desktop; do not commit any ledger to GitHub.
"""
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from save_readback_contract import (
    VALID_STATES, evaluate_post_save_readback, review_save_contract, validate_ledger,
)

SHA256 = re.compile(r"[a-f0-9]{64}\Z")
VERSION = "sfdc-local-operation-ledger-v1"

def _utc():
    return datetime.now(timezone.utc).isoformat()


def _private_path(path):
    """Refuse symlinked/absent/unexpected file and directory."""
    path = Path(path)
    if path.name != "operation_ledger_private.json":
        raise ValueError("Only dedicated private operation ledger may be modified")
    directory = Path.home() / ".sfdc_desktop"
    if path.parent.resolve() != directory.resolve() or path.is_symlink():
        raise ValueError("Ledger must be located in local private directory")
    if not path.is_file():
        raise FileNotFoundError("Existing private ledger required; do not invent history")
    return path


def _read(path):
    try:
        ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError("Missing, corrupt or unreadable ledger: HOLD") from exc
    validate_ledger(ledger)
    return ledger


@contextmanager
def exclusive_ledger(path):
    """Atomic OS directory lock. On crash, stale lock remains HOLD until manual audit.

    Another process cannot silently steal a stale lock after a timeout. No network
    lock, no saved Salesforce tokens, and no background processes.
    """
    path = _private_path(path)
    lock_path = path.with_name(path.name + ".lock")
    try:
        os.mkdir(lock_path)
    except FileExistsError as exc:
        raise RuntimeError("Operation journal is locked or previous run outcome unknown") from exc
    try:
        yield path
    finally:
        # If this process reaches finally, its open transaction has either fully
        # returned or raised. The durable record may still contain unknown outcome.
        os.rmdir(lock_path)


def _atomic_commit(path, ledger):
    validate_ledger(ledger)
    directory = path.parent
    name = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory,
                prefix=".operation_ledger_", suffix=".tmp", delete=False) as f:
            name = f.name
            json.dump(ledger, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        # On POSIX, fsync the containing directory to ensure the rename is durable.
        if os.name == "posix":
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def review_reservation(ledger, preflight, live, approval):
    """Pure decision: review reservation never grants or performs Salesforce Save."""
    status = review_save_contract(preflight, live, approval, ledger)["status"]
    if status != "READY_FOR_SEPARATE_MANUAL_SAVE_REVIEW_NOT_EXECUTION":
        return status, None
    entry = {
        "request_uid": preflight["request_uid"],
        "operation_fingerprint": preflight["operation_fingerprint"],
        "change_intent_fingerprint": preflight["change_intent_fingerprint"],
        "state": "PREPARED", "created_utc": _utc(),
        "save_performed_by_this_module": False,
    }
    # All entries are append-only identities; reject collisions again.
    validate_ledger({"version": VERSION, "entries": ledger["entries"] + [entry]})
    return "MANUAL_REVIEW_RESERVED_NO_SAVE", entry


def reserve_manual_review(path, preflight, live, approval):
    """Atomic reviewed reservation. NEVER clicks, connects to, or changes Salesforce."""
    with exclusive_ledger(path) as p:
        ledger = _read(p)  # Read only after locking, prevent concurrent stale reads.
        status, entry = review_reservation(ledger, preflight, live, approval)
        if entry is None:
            return {"status": status, "save_allowed": False,
                    "salesforce_save_performed": False}
        ledger["entries"].append(entry)
        _atomic_commit(p, ledger)
        return {"status": status, "save_allowed": False,
                "salesforce_save_performed": False}


def plan_outcome(ledger, uid, event, evidence=None):
    """Pure transition planning for an EXTERNAL, human-operated Save only.

    This module does not record a successful CRM write without authoritative
    readback proof; WRITE_OUTCOME_UNKNOWN can only move to verified reconciliation.
    """
    entries = validate_ledger(ledger)
    found = [e for e in entries if e["request_uid"] == uid]
    if len(found) != 1:
        raise ValueError("Exact operation UID missing or duplicate")
    old = found[0]
    state = old["state"]
    events = {
        "CANCEL_REVIEW": {"PREPARED"},
        "EXTERNAL_SAVE_STARTED": {"PREPARED"},
        "EXTERNAL_SAVE_OUTCOME_UNKNOWN": {"PENDING_WRITE"},
        "EXTERNAL_SAVE_REPORTED": {"PENDING_WRITE"},
        "MANUAL_HOLD": {"PREPARED", "PENDING_WRITE", "WRITE_OUTCOME_UNKNOWN", "READBACK_REQUIRED"},
        "VERIFY_READBACK": {"READBACK_REQUIRED", "WRITE_OUTCOME_UNKNOWN"},
    }
    if event not in events or state not in events[event]:
        raise ValueError("Unsafe or duplicate state transition")
    if event == "CANCEL_REVIEW":
        next_state = "CANCELLED"
    elif event == "EXTERNAL_SAVE_STARTED":
        # Strict human evidence: this is a recording of an externally begun
        # action. This module must not simulate or start it itself.
        if not isinstance(evidence, dict) or evidence.get("human_executed_write_started") is not True:
            raise ValueError("Human external-write start evidence required")
        next_state = "PENDING_WRITE"
    elif event == "EXTERNAL_SAVE_OUTCOME_UNKNOWN":
        next_state = "WRITE_OUTCOME_UNKNOWN"
    elif event == "EXTERNAL_SAVE_REPORTED":
        next_state = "READBACK_REQUIRED"
    elif event == "MANUAL_HOLD":
        next_state = "HOLD"
    elif event == "VERIFY_READBACK":
        if not isinstance(evidence, dict):
            raise ValueError("Verified reloaded Salesforce evidence required")
        status = evaluate_post_save_readback(evidence.get("approved"),
                                             evidence.get("refreshed"))
        if status != "READBACK_FIELDS_AND_LINKS_MATCH_REVIEW_REQUIRED":
            # Preserve unknown as unknown until genuine readback succeeds.
            raise ValueError("Post-Save readback mismatch or missing reload: " + status)
        next_state = "VERIFIED"
    else:
        raise ValueError("Unsupported event")
    result = {"version": VERSION, "entries": [dict(row) for row in entries]}
    index = next(i for i, e in enumerate(result["entries"]) if e["request_uid"] == uid)
    result["entries"][index] = {
        **result["entries"][index], "state": next_state, "updated_utc": _utc(),
    }
    validate_ledger(result)
    return result


def record_manual_outcome(path, uid, event, evidence=None):
    """Durably record a reviewed event; no external UI or Salesforce action."""
    with exclusive_ledger(path) as p:
        ledger = _read(p)
        updated = plan_outcome(ledger, uid, event, evidence)
        _atomic_commit(p, updated)
        return {"status": updated["entries"][
            next(i for i, e in enumerate(updated["entries"]) if e["request_uid"] == uid)]["state"],
                "save_allowed": False, "salesforce_save_performed": False}


if __name__ == "__main__":
    print("Offline durable journal only. NO Salesforce connection or Save action.")
