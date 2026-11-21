#!/usr/bin/env python3
"""Fail-closed forensic triage of Yahoo/Alpaca corporate-action discrepancies.

Reads the *same* persisted vendor histories; never rewrites prices, signals,
corporate-action events or security identity. A proposed cause is a diagnostic
observation, NOT an issuer-certified resolution, independent price adjustment,
or closing-auction finality approval.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import date
import json
from pathlib import Path

from corporate_actions_compare import MATCH_STATUSES, yahoo_actions
from corporate_actions_reference import VERSION as REFERENCE_VERSION
from daily20 import load_spec, write_json

VERSION = "daily20-corporate-action-forensics-v1"
EXPECTED_ISSUES = {
    "ALPACA_ONLY_EVENT_HOLD", "YAHOO_ONLY_EVENT_HOLD",
    "CROSS_PROVIDER_VALUE_CONFLICT_HOLD",
    "MULTIPLE_SAME_DAY_EVENTS_AMBIGUOUS_HOLD",
    "SOURCE_UNAVAILABLE_HOLD", "SOURCE_INCOMPLETE_HOLD",
    "CANDIDATE_SPLIT_FACTOR_UNRESOLVED_HOLD",
}
REPAIR_DIAGNOSTIC = "YAHOO_REPAIR_SUPPRESSED_DIVIDEND_OBSERVED"
SOURCE_BOUNDARY = "ALPACA_PROCESS_DATE_CUTOFF_POSSIBLE"
DUPLICATE = "SAME_EXDATE_IDENTICAL_RATES_DISTINCT_EVENT_IDS"


def _num(value):
    from decimal import Decimal, InvalidOperation
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value))
        return n if n.is_finite() else None
    except (ValueError, InvalidOperation, TypeError):
        return None


def _event_ref(reference, sym, day, typ):
    group = {"DIVIDEND": "cash_dividends",
             "SPLIT": "forward_splits"}
    accepted = {group[typ]} if typ == "DIVIDEND" else {
        "forward_splits", "reverse_splits"}
    return [
        x for x in reference.get("events", [])
        if x.get("symbol") == sym and x.get("ex_date") == day
        and x.get("type") in accepted
    ]


def triage(line, repaired, raw, source, source_status, cutoff):
    """Return typed diagnostic with source-side evidence; always holds."""
    sym, day, kind = line["symbol"], line["ex_date"], line["kind"]
    status = line["status"]
    raw_value = raw.get(day, {}).get(kind)
    repaired_value = repaired.get(day, {}).get(kind)
    if status in MATCH_STATUSES:
        return None
    if status not in EXPECTED_ISSUES:
        reason = "UNRECOGNIZED_COMPARISON_STATUS_HOLD"
    elif status == "ALPACA_ONLY_EVENT_HOLD":
        if (kind == "DIVIDEND" and raw_value is not None
                and repaired_value is not None
                and raw_value > 0 and repaired_value == 0):
            reason = REPAIR_DIAGNOSTIC
        else:
            reason = "ALPACA_ONLY_UNCONFIRMED_BY_EITHER_YAHOO_VARIANT"
    elif status == "YAHOO_ONLY_EVENT_HOLD":
        # A missing Alpaca record for a recent EX-date might be caused by the
        # process_date-bounded query; this is not an event-absence verdict.
        diff = (date.fromisoformat(cutoff)-date.fromisoformat(day)).days
        reason = SOURCE_BOUNDARY if 0 <= diff <= 14 else "YAHOO_ONLY_HISTORICAL_UNEXPLAINED"
    elif status == "MULTIPLE_SAME_DAY_EVENTS_AMBIGUOUS_HOLD":
        events = _event_ref(source, sym, day, kind)
        rates = [_num(x.get("rate")) for x in events]
        ids = [x.get("id") for x in events]
        if (len(events) >= 2 and all(x is not None for x in rates)
                and len(set(rates)) == 1 and len(set(ids)) == len(ids)):
            reason = DUPLICATE
        else:
            reason = "MULTIPLE_SAME_DAY_VALUES_OR_IDENTITIES_UNRESOLVED"
    elif status == "CROSS_PROVIDER_VALUE_CONFLICT_HOLD":
        reason = "ALPACA_VS_YAHOO_VALUE_CONFLICT_UNEXPLAINED"
    else:
        reason = "CROSS_PROVIDER_EVIDENCE_INCOMPLETE_HOLD"
    events = _event_ref(source, sym, day, kind)
    return {
        "symbol": sym, "ex_date": day, "kind": kind,
        "comparison_status": status,
        "diagnostic_reason": reason,
        "yahoo_repaired_event": str(repaired_value) if repaired_value is not None else None,
        "yahoo_raw_event": str(raw_value) if raw_value is not None else None,
        "alpaca_rate": line.get("alpaca_value") or None,
        "alpaca_event_ids": ";".join(
            x.get("id", "") for x in events if isinstance(x.get("id"), str)),
        "alpaca_process_dates": ";".join(
            x.get("process_date", "") for x in events
            if isinstance(x.get("process_date"), str)),
        "alpaca_query_end_process_date": cutoff,
        "source_status": source_status,
        "vendor_policy_effect_observed": reason == REPAIR_DIAGNOSTIC,
        "resolved_by_issuer_evidence": False,
        "independent_price_factor_certified": False,
    }


def build(factor_dir, ref, compare_report, comparison_rows, spec):
    if ref.get("version") != REFERENCE_VERSION:
        raise ValueError("CA_FORENSICS_REFERENCE_VERSION_MISMATCH")
    if (ref.get("session") != compare_report.get("session")
            or ref.get("finality_verified") != 0
            or compare_report.get("finality_verified") != 0):
        raise ValueError("CA_FORENSICS_SESSION_OR_FINALITY_GOVERNANCE_INVALID")
    if (compare_report.get("research_only") is not True
            or compare_report.get("independent_factor_certification") != 0):
        raise ValueError("CA_FORENSICS_PARENT_NOT_UNCERTIFIED")
    required = [s for s in spec["core"] + spec["context"] if s != "^VIX"]
    if len(required) != 25 or set(ref.get("queried_symbols", [])) != set(required):
        raise ValueError("CA_FORENSICS_UNIVERSE_MISMATCH")
    base = Path(factor_dir)
    lineage = json.loads((base / "report.json").read_text())
    if lineage.get("session") != ref["session"]:
        raise ValueError("CA_FORENSICS_LINEAGE_SESSION_MISMATCH")
    source_rows = {row["symbol"]: row for row in lineage["rows"]}
    if set(source_rows) != set(required):
        raise ValueError("CA_FORENSICS_LINEAGE_SYMBOL_MISMATCH")
    cutoff = ref["query_end_process_date"]
    if date.fromisoformat(cutoff).isoformat() != cutoff:
        raise ValueError("CA_FORENSICS_PROCESS_CUTOFF_INVALID")
    issue_lines = []
    for row in comparison_rows:
        if row["symbol"] not in source_rows:
            raise ValueError("CA_FORENSICS_UNKNOWN_COMPARISON_SYMBOL")
        if row["status"] not in MATCH_STATUSES:
            issue_lines.append(row)
    cases = []
    cache = {}
    for row in issue_lines:
        symbol = row["symbol"]
        if symbol not in cache:
            # Separate raw and production-repair Yahoo records. This is NOT
            # an independent third data vendor, only policy-lineage evidence.
            raw, raw_sha = yahoo_actions(
                base, symbol, {"csv_gzip_file": symbol.lower()+".csv.gz"})
            repaired, repair_sha = yahoo_actions(
                base, symbol, source_rows[symbol])
            cache[symbol] = (repaired, raw, raw_sha, repair_sha)
        repaired, raw, _rawsha, _repairsha = cache[symbol]
        case = triage(row, repaired, raw, ref, ref["status"], cutoff)
        if case is None:
            raise ValueError("CA_FORENSICS_UNEXPECTED_MATCH_STATUS")
        cases.append(case)
    # Only rows of unresolved comparisons are triaged, not the 766 numeric
    # candidate agreements. Same-group source IDs remain distinct and unsummed.
    if len(cases) + sum(r["status"] in MATCH_STATUSES for r in comparison_rows) != len(comparison_rows):
        raise ValueError("CA_FORENSICS_EXCEPTIONS_NOT_EXHAUSTIVE")
    links = []
    for x in ref.get("unmapped_historical_identity_examples", []):
        if not isinstance(x, dict):
            raise ValueError("CA_FORENSICS_IDENTITY_NOT_OBJECT")
        links.append({
            "type": x.get("group"),
            "event_id": x.get("event_id"),
            "process_date": x.get("process_date"),
            "old_symbol": x.get("identity_roles", {}).get("old_symbol"),
            "new_symbol": x.get("identity_roles", {}).get("new_symbol"),
            "acquiree_symbol": x.get("identity_roles", {}).get("acquiree_symbol"),
            "acquirer_symbol": x.get("identity_roles", {}).get("acquirer_symbol"),
            "role_based_candidates": x.get("queried_symbol_role_candidates", {}),
            "schema_role_classification": x.get("identity_schema", "NOT_RECORDED_IN_LEGACY_REFERENCE"),
            "issuer_identity_certified": False,
        })
    counts = dict(sorted(Counter(c["diagnostic_reason"] for c in cases).items()))
    exact_lineage = [c for c in cases if c["vendor_policy_effect_observed"]]
    return {
        "report": {
            "version": VERSION, "session": ref["session"],
            "research_only": True, "production_writes": False, "strategy_promoted": False,
            "finality_verified": 0, "independent_factor_certification": 0,
            "issuer_identity_certified": 0, "required_symbols": 25,
            "reference_status": ref["status"],
            "source_date_semantics": "ALPACA_QUERY_FILTERS_PROCESS_DATE_NOT_EX_DATE",
            "review_exception_count": len(cases),
            "exception_comparison_status_counts": dict(sorted(
                Counter(c["comparison_status"] for c in cases).items())),
            "review_reason_counts": counts,
            "yahoo_repair_suppression_observed": len(exact_lineage),
            "yahoo_repair_suppression_symbols": sorted(set(c["symbol"] for c in exact_lineage)),
            "issue_resolutions_issuer_verified": 0,
            "missing_generic_symbol_events": ref.get("unmapped_historical_identity_count", 0),
            "identity_role_schema_events": ref.get("role_based_identity_event_count", 0),
            "identity_candidate_link_events": ref.get("queried_symbol_role_link_candidates", 0),
            "identity_examples_preserved": len(links),
            "identity_source_report_complete": (
                len(links) == ref.get("unmapped_historical_identity_count", 0)),
            "status": "CORPORATE_ACTION_EXCEPTION_FORENSICS_HOLD",
        },
        "cases": cases, "links": links,
    }


def write_csv(path, rows, headers):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, dict)
                             else v for k, v in row.items()})


def run(factor_dir, reference_path, comparison_dir, out_dir, spec=None):
    spec = spec or load_spec()
    compare_dir = Path(comparison_dir)
    ref = json.loads(Path(reference_path).read_text())
    parent = json.loads((compare_dir/"report.json").read_text())
    with (compare_dir/"event_comparison.csv").open(newline="",encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    result = build(factor_dir, ref, parent, rows, spec)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out/"report.json", result["report"])
    write_csv(out/"review_queue.csv", result["cases"], [
        "symbol", "ex_date", "kind", "comparison_status", "diagnostic_reason",
        "yahoo_repaired_event", "yahoo_raw_event", "alpaca_rate",
        "alpaca_event_ids", "alpaca_process_dates", "alpaca_query_end_process_date",
        "source_status", "vendor_policy_effect_observed",
        "resolved_by_issuer_evidence", "independent_price_factor_certified"])
    write_csv(out/"identity_links.csv", result["links"], [
        "type", "event_id", "process_date", "old_symbol", "new_symbol",
        "acquiree_symbol", "acquirer_symbol", "role_based_candidates",
        "schema_role_classification", "issuer_identity_certified"])
    return result["report"]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--factor-dir",required=True)
    p.add_argument("--reference",required=True)
    p.add_argument("--comparison-dir",required=True)
    p.add_argument("--out-dir",required=True)
    a=p.parse_args()
    r=run(a.factor_dir,a.reference,a.comparison_dir,a.out_dir)
    print("DAILY20_CA_FORENSICS",r["review_exception_count"],"exceptions",
          r["yahoo_repair_suppression_observed"],"repair-policy cases",
          r["missing_generic_symbol_events"],"role-based identity events",
          "FINALITY 0/26 HOLD")


if __name__=="__main__":
    main()
