#!/usr/bin/env python3
"""Validate issuer cash-gap governance without requiring external source availability."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

VERSION = "daily20-issuer-ca-gap-workflow-gate-v1"
TARGETS = {("QQQ", "2018-06-18"), ("QLD", "2023-09-20")}
VERIFIED = "SOURCE_BYTES_AND_ANCHORS_VERIFIED_PAYMENT_UNCERTIFIED"
ALLOWED_SOURCE_STATES = {
    VERIFIED,
    "SOURCE_NOT_FETCHED_HOLD",
    "SOURCE_ANCHORS_MISSING_HOLD",
    "SOURCE_HASH_MISSING_HOLD",
    "SOURCE_RAW_BYTES_MISSING_HOLD",
}

def validate(report: dict) -> dict:
    if not isinstance(report, dict):
        raise ValueError("GAP_GATE_REPORT_NOT_OBJECT")
    if (report.get("version") != "daily20-issuer-ca-gap-audit-v1"
            or report.get("status") != "ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD"):
        raise ValueError("GAP_GATE_SCHEMA_OR_STATUS_INVALID")
    if (report.get("research_only") is not True
            or report.get("production_writes") is not False
            or report.get("strategy_promoted") is not False
            or report.get("issuer_payments_certified") != 0
            or report.get("source_finality_verified") != 0
            or report.get("unarchived_research_leads_are_certified") is not False):
        raise ValueError("GAP_GATE_GOVERNANCE_OR_FINALITY_INVALID")
    events = report.get("events")
    if not isinstance(events, list) or len(events) != len(TARGETS):
        raise ValueError("GAP_GATE_EVENT_COUNT_INVALID")
    seen = set()
    missing = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("GAP_GATE_EVENT_NOT_OBJECT")
        key = (event.get("symbol"), event.get("ex_date"))
        if key not in TARGETS or key in seen:
            raise ValueError("GAP_GATE_EVENT_SET_INVALID")
        seen.add(key)
        if (event.get("research_hold") is not True
                or event.get("actual_payment_certified") is not False
                or event.get("independent_adjustment_factor_certified") is not False
                or event.get("independent_close_certified") is not False
                or event.get("issuer_ex_date_and_amount_jointly_certified") is not False):
            raise ValueError("GAP_GATE_EVENT_PROMOTION_INVALID")
        state = event.get("archived_evidence_status")
        if state not in ALLOWED_SOURCE_STATES:
            raise ValueError("GAP_GATE_SOURCE_STATE_UNKNOWN")
        if state != VERIFIED:
            missing.append({"symbol": key[0], "ex_date": key[1], "state": state})
    if seen != TARGETS:
        raise ValueError("GAP_GATE_EVENT_SET_INCOMPLETE")
    complete = not missing
    if type(report.get("both_archived_sources_verified")) is not bool:
        raise ValueError("GAP_GATE_ARCHIVE_FLAG_INVALID")
    if report["both_archived_sources_verified"] is not complete:
        raise ValueError("GAP_GATE_ARCHIVE_FLAG_DISAGREES_WITH_EVENTS")
    return {
        "version": VERSION,
        "workflow_gate": "PASS",
        "evidence_state": "COMPLETE_UNCERTIFIED" if complete else "INCOMPLETE_HOLD",
        "both_archived_sources_verified": complete,
        "missing_source_events": missing,
        "downstream_research_may_continue": True,
        "research_only": True,
        "production_writes": False,
        "strategy_promoted": False,
        "issuer_payments_certified": 0,
        "source_finality_verified": 0,
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True)
    p.add_argument("--out")
    args = p.parse_args()
    result = validate(json.loads(Path(args.report).read_text(encoding="utf-8")))
    if args.out:
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DAILY20_DIVIDEND_GAP_GATE", result["workflow_gate"],
          result["evidence_state"], "missing", len(result["missing_source_events"]),
          "downstream", result["downstream_research_may_continue"],
          "CERTIFIED 0/26 HOLD")

if __name__ == "__main__":
    main()
