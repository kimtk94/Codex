#!/usr/bin/env python3
"""Compare Yahoo corporate-action observations with separately sourced Alpaca.

Cash dividend and split matching is per ex-date, NOT process date.
Cross-provider numeric agreement is research evidence ONLY: process-date lag,
historical symbol/issuer continuity, incomplete action types, adjustments,
and split-adjusted Yahoo Close remain uncertified. Never upgrade source finality.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import gzip
import json
from pathlib import Path

from daily20 import load_spec, write_json
from corporate_actions_reference import VERSION as REFERENCE_VERSION

VERSION = "daily20-corporate-action-crosscheck-v1"
DIVIDEND_TOLERANCE = Decimal("0.0001")
SPLIT_TOLERANCE = Decimal("0.0000001")
TYPES = {"cash_dividends": "DIVIDEND",
         "forward_splits": "SPLIT", "reverse_splits": "SPLIT"}


def decimal_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        x = Decimal(str(value))
        return x if x.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def yahoo_actions(root, symbol, row):
    file_name = row.get("repaired_csv_gzip_file") or row.get("csv_gzip_file")
    if not isinstance(file_name, str) or file_name != Path(file_name).name:
        raise ValueError("YAHOO_FACTOR_CSV_NAME_UNSAFE")
    if file_name not in {symbol.lower()+".csv.gz",
                         symbol.lower()+"_repaired.csv.gz"}:
        raise ValueError("YAHOO_FACTOR_CSV_SYMBOL_MISMATCH")
    import hashlib
    raw = (root / file_name).read_bytes()
    with gzip.open(root / file_name, "rt", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"session", "yahoo_dividend", "yahoo_stock_split"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("YAHOO_CA_CSV_SCHEMA_INCOMPLETE")
        data = list(reader)
    if not data:
        raise ValueError("YAHOO_CA_CSV_EMPTY")
    observed = {}
    for r in data:
        day = r["session"]
        if date.fromisoformat(day).isoformat() != day or day in observed:
            raise ValueError("YAHOO_CA_CSV_DUPLICATE_OR_BAD_DATE")
        div = decimal_number(r["yahoo_dividend"])
        split = decimal_number(r["yahoo_stock_split"])
        if div is None or split is None or split < 0:
            raise ValueError("YAHOO_CA_CSV_BAD_EVENT_VALUE")
        observed[day] = {"DIVIDEND": div, "SPLIT": split}
    return observed, hashlib.sha256(raw).hexdigest()


def alpaca_action(e):
    kind = TYPES.get(e["type"])
    if kind is None:
        return None, None, "OTHER_ACTION_UNSUPPORTED"
    exdate = e.get("ex_date")
    try:
        if date.fromisoformat(exdate).isoformat() != exdate:
            return kind, None, "EX_DATE_INVALID"
    except (TypeError, ValueError):
        return kind, None, "EX_DATE_MISSING"
    if kind == "DIVIDEND":
        value = decimal_number(e.get("rate"))
        if value is None or value <= 0:
            return kind, exdate, "DIVIDEND_RATE_INVALID"
        currency = e.get("currency")
        if currency not in (None, "", "USD"):
            return kind, exdate, "DIVIDEND_CURRENCY_NOT_USD"
        # Currency missing is possible but cannot authenticate denomination.
        if currency in (None, ""):
            return kind, exdate, "DIVIDEND_CURRENCY_UNATTESTED"
    else:
        old, new = decimal_number(e.get("old_rate")), decimal_number(e.get("new_rate"))
        if old is None or new is None or old <= 0 or new <= 0:
            return kind, exdate, "SPLIT_RATIO_INVALID"
        value = new / old
    return kind, exdate, value


def compare_one(symbol, observed, events, reference_ok, *, digest=None):
    output = []
    by_key = {}
    excluded = []
    unsupported = []
    days = sorted(observed)
    for e in events:
        typ, exdate, value = alpaca_action(e)
        if typ is None:
            unsupported.append({"type": e.get("type"), "ex_date": e.get("ex_date"),
                                "id": e.get("id")})
            continue
        if not isinstance(value, Decimal):
            excluded.append({"type": e.get("type"), "ex_date": exdate, "id": e.get("id"),
                             "reason": value})
            continue
        if exdate not in observed:
            excluded.append({"type": e.get("type"), "ex_date": exdate, "id": e.get("id"),
                             "reason": "EX_DATE_NOT_IN_YAHOO_OBSERVED_SESSION"})
            continue
        by_key.setdefault((exdate, typ), []).append((e, value))
    yahoo_keys = {
        (day, kind) for day, values in observed.items()
        for kind in ("DIVIDEND", "SPLIT") if values[kind] != 0
    }
    keys = sorted(yahoo_keys | set(by_key))
    for day, kind in keys:
        yahoo = observed[day][kind]
        candidates = by_key.get((day, kind), [])
        if not reference_ok:
            status, alpaca = "SOURCE_INCOMPLETE_HOLD", None
        elif len(candidates) > 1:
            status, alpaca = "MULTIPLE_SAME_DAY_EVENTS_AMBIGUOUS_HOLD", None
        elif len(candidates) == 0:
            status, alpaca = "YAHOO_ONLY_EVENT_HOLD", None
        else:
            alpaca = candidates[0][1]
            tol = DIVIDEND_TOLERANCE if kind == "DIVIDEND" else SPLIT_TOLERANCE
            status = ("CROSS_PROVIDER_NUMERIC_MATCH_RESEARCH_ONLY"
                      if abs(yahoo-alpaca) <= tol else "CROSS_PROVIDER_VALUE_CONFLICT_HOLD")
            if yahoo == 0:
                status = "ALPACA_ONLY_EVENT_HOLD"
        output.append({
            "symbol": symbol, "ex_date": day, "kind": kind,
            "yahoo_value": str(yahoo), "alpaca_value": str(alpaca) if alpaca is not None else None,
            "alpaca_count": len(candidates),
            "status": status,
        })
    count = {}
    for row in output:
        count[row["status"]] = count.get(row["status"], 0) + 1
    coverage = ("NO_ALPACA_REFERENCE_HOLD" if not reference_ok else
                "EVENT_DIFFERENCES_OR_INCOMPLETE_HOLD" if
                any(row["status"] != "CROSS_PROVIDER_NUMERIC_MATCH_RESEARCH_ONLY" for row in output)
                or excluded or unsupported else
                "ALL_OBSERVED_EVENTS_NUMERICALLY_MATCH_UNCERTIFIED")
    return {
        "symbol": symbol, "status": coverage,
        "yahoo_first_session": days[0], "yahoo_last_session": days[-1],
        "yahoo_dividend_events": sum(v["DIVIDEND"] != 0 for v in observed.values()),
        "yahoo_split_events": sum(v["SPLIT"] != 0 for v in observed.values()),
        "alpaca_reference_events": len(events),
        "match_count": count.get("CROSS_PROVIDER_NUMERIC_MATCH_RESEARCH_ONLY", 0),
        "status_counts": count,
        "unsupported_action_count": len(unsupported),
        "unsupported_examples": unsupported[:8],
        "unmatched_or_incomplete_action_count": len(excluded),
        "unmatched_examples": excluded[:8],
        "source_csv_gzip_sha256": digest,
        "factor_independently_certified": False,
    }, output


def run(factor_dir, reference_path, out_dir, *, spec=None):
    spec = spec or load_spec()
    factor_dir, out_dir = Path(factor_dir), Path(out_dir)
    ref = json.loads(Path(reference_path).read_text())
    factor_report = json.loads((factor_dir / "report.json").read_text())
    if ref.get("version") != REFERENCE_VERSION:
        raise RuntimeError("CA_REFERENCE_VERSION_MISMATCH")
    if factor_report.get("session") != ref.get("session"):
        raise RuntimeError("CA_REFERENCE_SESSION_MISMATCH")
    names = [x for x in spec["core"] + spec["context"] if x != "^VIX"]
    if len(names) != 25 or set(ref.get("queried_symbols", [])) != set(names):
        raise RuntimeError("CA_REFERENCE_SYMBOL_COVERAGE_MISMATCH")
    if factor_report.get("finality_verified") != 0 or ref.get("finality_verified") != 0:
        raise RuntimeError("CA_RESEARCH_REFERENCE_CANNOT_VERIFY_FINALITY")
    if ref.get("factor_independently_certified") != 0:
        raise RuntimeError("CA_REFERENCE_SELF_ATTESTATION_FORBIDDEN")
    rows_by_symbol = {r["symbol"]: r for r in factor_report["rows"]}
    if set(rows_by_symbol) != set(names):
        raise RuntimeError("CA_YAHOO_25_SYMBOL_REPORT_MISMATCH")
    valid_reference = ref.get("status") == "ALPACA_ACTIONS_RETRIEVED_UNCERTIFIED"
    events = ref.get("events", [])
    if not isinstance(events, list):
        raise RuntimeError("CA_EVENTS_NOT_LIST")
    by_symbol = {s: [] for s in names}
    for event in events:
        if not isinstance(event, dict) or event.get("symbol") not in by_symbol:
            raise RuntimeError("CA_EVENT_UNKNOWN_SYMBOL_OR_SCHEMA")
        by_symbol[event["symbol"]].append(event)
    lines, summaries = [], []
    for symbol in names:
        try:
            observed, digest = yahoo_actions(factor_dir, symbol, rows_by_symbol[symbol])
            summary, detail = compare_one(
                symbol, observed, by_symbol[symbol], valid_reference,
                digest=digest)
            lines.extend(detail)
        except (ValueError, KeyError, OSError, EOFError, TypeError) as exc:
            summary = {"symbol": symbol, "status": "YAHOO_FACTOR_EVIDENCE_UNAVAILABLE_HOLD",
                       "error_class": type(exc).__name__,
                       "factor_independently_certified": False}
        summaries.append(summary)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "event_comparison.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "symbol", "ex_date", "kind", "yahoo_value", "alpaca_value",
            "alpaca_count", "status"])
        writer.writeheader()
        writer.writerows(lines)
    report = {
        "version": VERSION, "session": ref["session"],
        "reference_status": ref.get("status"),
        "reference_page_count": ref.get("page_count", 0),
        "reference_page_sha256": ref.get("page_sha256", []),
        "yahoo_source": "Yahoo/yfinance repair=true where required",
        "candidate_action_source": "Alpaca Market Data Corporate Actions v1",
        "process_date_not_ex_date_query": True,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False,
        "independent_factor_certification": 0,
        "finality_verified": 0, "required": 25,
        "yahoo_factor_sources_observed": sum(
            x.get("status") != "YAHOO_FACTOR_EVIDENCE_UNAVAILABLE_HOLD"
            for x in summaries),
        "matched_ex_date_events": sum(x.get("match_count", 0) for x in summaries),
        "alpaca_events_observed": len(events),
        "status": "CORPORATE_ACTION_CROSSCHECK_RESEARCH_HOLD",
        "symbols": summaries,
    }
    write_json(out_dir / "report.json", report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--factor-dir", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--out-dir", required=True)
    a = p.parse_args()
    r = run(a.factor_dir, a.reference, a.out_dir)
    print("DAILY20_CA_CROSSCHECK", r["reference_status"],
          "matched_events", r["matched_ex_date_events"],
          "yahoo_sources", r["yahoo_factor_sources_observed"],
          "CERTIFIED", r["independent_factor_certification"], "/25 HOLD")


if __name__ == "__main__":
    main()
