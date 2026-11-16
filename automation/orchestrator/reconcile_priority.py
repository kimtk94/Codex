#!/usr/bin/env python3
"""Conservatively join sanitized monthly mirror evidence to the 9-domain CI queue.

Revenue mirror consistency is NOT proof of QQ-original invoices or Feishu Base
readback. A failed historical workflow and newer mirror snapshot remain separate
pieces of evidence. No amount, customer identity or private row is propagated.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re

MAX_RECEIPT_AGE_HOURS = 6  # evidence-file lifespan; separate from mirror snapshot age
KST = dt.timezone(dt.timedelta(hours=9))

STATES = {
    "MIRROR_3WAY_PARITY_AGED",
    "MIRROR_3WAY_PARITY_RECENT",
    "MIRROR_UNAVAILABLE_OR_MISMATCH",
}
ACTIONS = {
    "MIRROR_3WAY_PARITY_AGED": (
        110, "RECHECK_AGED_REVENUE_MIRROR_AND_ORIGINAL_SOURCE_READBACK"),
    "MIRROR_3WAY_PARITY_RECENT": (
        20, "COMPARE_RECENT_REVENUE_MIRROR_WITH_ORIGINAL_SOURCE_READBACK"),
    "MIRROR_UNAVAILABLE_OR_MISMATCH": (
        120, "DIAGNOSE_MIRROR_SOURCE_UNAVAILABLE_OR_MISMATCH"),
    "MIRROR_RECEIPT_MISSING": (
        115, "RESTORE_REVENUE_MIRROR_READONLY_EVIDENCE"),
    "MIRROR_RECEIPT_INVALID": (
        125, "REVIEW_INVALID_REVENUE_MIRROR_RECEIPT"),
    "MIRROR_RECEIPT_STALE": (
        130, "REFRESH_EXPIRED_REVENUE_MIRROR_RECEIPT_READONLY"),
}
MONTH = re.compile(r"^20\d{2}-(?:0[1-9]|1[0-2])$")


def validate_receipt(data: dict, *, observed_at: dt.datetime | None = None) -> str:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("MIRROR_RECEIPT_SCHEMA")
    if (data.get("source_scope") != "GOOGLE_SHEETS_MIRROR_ONLY"
            or data.get("business_source_sink_verification") != "NOT_VERIFIED"
            or data.get("business_source_original_probed") is not False
            or data.get("feishu_base_sink_readback_probed") is not False
            or data.get("no_business_writes") is not True):
        raise ValueError("MIRROR_RECEIPT_UNSAFE_SCOPE")
    state = data.get("status")
    if state not in STATES or not isinstance(data.get("month"), str) or not MONTH.fullmatch(data["month"]):
        raise ValueError("MIRROR_RECEIPT_BAD_STATUS")
    checked = data.get("checked_at")
    if not isinstance(checked, str):
        raise ValueError("MIRROR_RECEIPT_TIME_MISSING")
    try:
        timestamp = dt.datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("MIRROR_RECEIPT_TIME_INVALID") from exc
    if timestamp.utcoffset() is None:
        raise ValueError("MIRROR_RECEIPT_NAIVE_TIMESTAMP")
    # A receipt can be from the current run but not from a future timestamp.
    now = observed_at or dt.datetime.now(dt.timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("MIRROR_OBSERVATION_TIMEZONE_REQUIRED")
    if timestamp > now + dt.timedelta(minutes=10):
        raise ValueError("MIRROR_RECEIPT_FUTURE_TIMESTAMP")
    # This workflow always audits its local current calendar month. Prevent
    # a recent receipt about an older month from counting as a fresh audit.
    if data["month"] != timestamp.astimezone(KST).strftime("%Y-%m"):
        raise ValueError("MIRROR_RECEIPT_WRONG_CALENDAR_MONTH")
    if state.startswith("MIRROR_3WAY_PARITY_"):
        if (data.get("source_tabs_checked") != 3 or data.get("three_way_aggregate_parity") is not True
                or data.get("snapshot_age_state") != (
                    "AGED_RECHECK" if state.endswith("_AGED") else "WITHIN_REVIEW_THRESHOLD")):
            raise ValueError("MIRROR_PARITY_CLAIM_UNSUPPORTED")
    # Do not confuse receipt creation freshness with the independent 48-hour
    # snapshot clock. An expired receipt cannot attest to today's mirror read.
    if now - timestamp > dt.timedelta(hours=MAX_RECEIPT_AGE_HOURS):
        return "MIRROR_RECEIPT_STALE"
    return state


def with_mirror_evidence(report: dict, receipt_path: Path | None = None) -> dict:
    """Score next read-only audit; do not turn any CI or mirror state into business PASS.

    receipt_path=None means PR CI intentionally lacks private mirror evidence.
    A supplied but missing/broken path is a real evidence gap and has priority.
    """
    item = next((x for x in report["queue"] if x.get("domain") == "payment_revenue"), None)
    if item is None:
        raise ValueError("REVENUE_DOMAIN_NOT_PRESENT")
    if receipt_path is None:
        state = "MIRROR_NOT_COLLECTED_PR"
    else:
        try:
            payload = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
            state = validate_receipt(payload)
        except FileNotFoundError:
            state = "MIRROR_RECEIPT_MISSING"
        except (ValueError, TypeError, KeyError, OSError):
            state = "MIRROR_RECEIPT_INVALID"
    item["revenue_mirror_signal"] = state
    item["business_source_checked"] = False
    item["business_sink_checked"] = False
    item["business_freshness"] = "NOT_VERIFIED"
    if state in ACTIONS:
        min_priority, action = ACTIONS[state]
        item["priority"] = max(item["priority"], min_priority)
        # If the recent mirror is internally consistent but a historical CI
        # run failed, investigate the old failure AND current originals.
        if state == "MIRROR_3WAY_PARITY_RECENT" and item["signal"] == "CI_FAILED":
            item["next_safe_action"] = "COMPARE_FAILED_REVENUE_CI_WITH_RECENT_MIRROR_AND_ORIGINALS"
        else:
            item["next_safe_action"] = action
    order = {d["domain"]: i for i, d in enumerate(report["queue"])}
    report["queue"].sort(key=lambda x: (-x["priority"], order[x["domain"]]))
    report["next_review"] = report["queue"][0]
    report["revenue_mirror_evidence"] = state
    report["business_source_sink_verification"] = "NOT_VERIFIED"
    report["auto_execute_business_writes"] = False
    report["auto_merge_pr"] = False
    return report
