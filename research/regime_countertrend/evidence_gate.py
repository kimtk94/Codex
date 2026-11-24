"""Strict evidence admission: SHADOW and mirrored-only records are not real fills."""
import hashlib
import json
from pathlib import Path

REQUIRED={"origin","execution_mode","independently_reconciled","broker_observed_at_utc","sha256_trades","sha256_bars"}

def classify_evidence(trades_path,bars_path,attestation_path):
    trade,bars,att=(Path(trades_path),Path(bars_path),Path(attestation_path))
    if not trade.is_file() or not bars.is_file():
        return {"status":"HOLD_MISSING_ACTUAL_FILLS_OR_BARS","real_fill_validated":False}
    if not att.is_file():
        return {"status":"HOLD_MISSING_BROKER_ATTESTATION","real_fill_validated":False}
    try:
        meta=json.loads(att.read_text())
    except (ValueError,UnicodeError):
        return {"status":"HOLD_INVALID_ATTESTATION","real_fill_validated":False}
    if not isinstance(meta,dict) or not REQUIRED.issubset(meta):
        return {"status":"HOLD_INCOMPLETE_ATTESTATION","real_fill_validated":False}
    if (meta.get("origin")!="BROKER_INDEPENDENT" or
        meta.get("execution_mode")!="LIVE" or
        meta.get("independently_reconciled") is not True):
        return {"status":"HOLD_SHADOW_OR_UNVERIFIED_MIRROR","real_fill_validated":False}
    try:
        sha_trades=hashlib.sha256(trade.read_bytes()).hexdigest()
        sha_bars=hashlib.sha256(bars.read_bytes()).hexdigest()
    except OSError:
        return {"status":"HOLD_DATA_UNREADABLE","real_fill_validated":False}
    if sha_trades!=meta["sha256_trades"] or sha_bars!=meta["sha256_bars"]:
        return {"status":"HOLD_ATTESTED_HASH_MISMATCH","real_fill_validated":False}
    return {"status":"PASS_EVIDENCE_CONTRACT_ONLY","real_fill_validated":False,
            "note":"Attestation format and hashes pass. Trade-level linkage, fill provenance and bar coverage must be independently checked."}
