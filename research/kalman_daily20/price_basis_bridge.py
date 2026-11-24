#!/usr/bin/env python3
"""Reconcile *provenance*, not equivalence, of 26 Daily20 close prices.

Research only. Alpaca venue M is raw, Yahoo Close is vendor split-adjusted,
Yahoo Adj Close is vendor dividend+split adjusted, while the Daily20 input
is auto-adjusted and may have repair=True. These bases are not interchangeable
without an *independently* certified corporate action factor.
"""
from __future__ import annotations

import argparse
import csv
import gzip
from hashlib import sha256
import io
import json
import math
from pathlib import Path

from daily20 import load_spec, write_json

VERSION = "daily20-price-basis-bridge-v1"
FACTOR_VERSION = "daily20-yahoo-factor-lineage-v2"
SOURCE_VERSION = "daily20-source-finality-v1"
VENUE_VERSION = "daily20-primary-listing-evidence-v1"
MAX_CSV_COMPRESSED = 8_000_000
MAX_CSV_DECOMPRESSED = 25_000_000
CENTS_TOLERANCE = 0.005
RAW_TOLERANCE = 1e-7


def _require(cond, code):
    if not cond:
        raise ValueError(code)


def _objects_by_symbol(rows, expected, label):
    _require(isinstance(rows, list), label + "_NOT_LIST")
    result = {}
    for item in rows:
        _require(isinstance(item, dict), label + "_ROW_NOT_OBJECT")
        symbol = item.get("symbol")
        _require(symbol in expected and symbol not in result,
                 label + "_SYMBOL_DUPLICATED_OR_UNKNOWN")
        result[symbol] = item
    _require(set(result) == set(expected), label + "_COVERAGE_INCOMPLETE")
    return result


def _price(value, code):
    _require(not isinstance(value, bool), code)
    try:
        v = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(code) from exc
    _require(math.isfinite(v) and v > 0, code)
    return v


def read_yahoo_trace(base, symbol, item, session):
    """Verify original *unrepaired* Yahoo trace bytes and its dated row.

    No verified bytes => no inferred factor. CSV is read separately and never
    used as a reference for a certified independent adjustment.
    """
    filename = item.get("csv_gzip_file")
    if filename is None:
        return {"status": "YAHOO_VENDOR_TRACE_UNAVAILABLE_HOLD"}
    _require(filename == symbol.lower() + ".csv.gz",
             "UNEXPECTED_VENDOR_TRACE_FILENAME")
    expected_sha = item.get("serialized_csv_sha256")
    _require(isinstance(expected_sha, str) and len(expected_sha) == 64,
             "VENDOR_TRACE_HASH_MISSING")
    path = Path(base) / filename
    _require(path.is_file() and path.stat().st_size <= MAX_CSV_COMPRESSED,
             "VENDOR_TRACE_MISSING_OR_OVERSIZE")
    try:
        with gzip.open(path, "rb") as f:
            blob = f.read(MAX_CSV_DECOMPRESSED + 1)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise ValueError("VENDOR_TRACE_GZIP_CORRUPT") from exc
    _require(len(blob) <= MAX_CSV_DECOMPRESSED,
             "VENDOR_TRACE_EXPANDED_OVERSIZE")
    _require(sha256(blob).hexdigest() == expected_sha,
             "VENDOR_TRACE_SHA256_MISMATCH")
    try:
        reader = csv.DictReader(io.StringIO(blob.decode("utf-8")))
        required = ("session", "yahoo_close_split_adjusted",
                    "yahoo_adj_close", "yahoo_adj_over_close")
        _require(reader.fieldnames is not None and
                 all(field in reader.fieldnames for field in required),
                 "VENDOR_TRACE_SCHEMA_INVALID")
        matched = []
        dates = set()
        for row in reader:
            day = row.get("session")
            _require(day not in dates, "VENDOR_TRACE_DUPLICATED_DATE")
            dates.add(day)
            if day == session:
                matched.append(row)
    except UnicodeDecodeError as exc:
        raise ValueError("VENDOR_TRACE_ENCODING_INVALID") from exc
    if not matched:
        return {"status": "YAHOO_ASOF_SESSION_MISSING_HOLD",
                "original_csv_sha256": expected_sha}
    _require(len(matched) == 1, "VENDOR_TRACE_ASOF_NOT_UNIQUE")
    row = matched[0]
    close = _price(row["yahoo_close_split_adjusted"], "VENDOR_CLOSE_INVALID")
    adjusted = _price(row["yahoo_adj_close"], "VENDOR_ADJUSTED_CLOSE_INVALID")
    ratio = _price(row["yahoo_adj_over_close"], "VENDOR_RATIO_INVALID")
    _require(math.isclose(adjusted / close, ratio, rel_tol=1e-8, abs_tol=1e-9),
             "VENDOR_RATIO_NOT_SELF_CONSISTENT")
    return {
        "status": "YAHOO_VENDOR_TRACE_OBSERVED_UNCERTIFIED",
        "original_csv_sha256": expected_sha,
        "vendor_close_split_adjusted": close,
        "vendor_adj_close": adjusted,
        "vendor_adj_over_vendor_close": ratio,
        "dividend_and_split_origin": "YAHOO_UNREPAIRED_RESEARCH_ONLY",
    }


def compare(spec, finality, venue, lineage, trace_dir):
    names = list(spec["core"]) + list(spec["context"])
    equities = [name for name in names if name != "^VIX"]
    _require(len(names) == 26 and len(set(names)) == 26 and
             len(equities) == 25, "PRICE_BRIDGE_20_PLUS_6_EXPECTED")
    session = finality.get("session")
    _require(session == venue.get("session") == lineage.get("session"),
             "PRICE_BRIDGE_SESSION_MISMATCH")
    _require(finality.get("version") == SOURCE_VERSION and
             venue.get("version") == VENUE_VERSION and
             lineage.get("version") == FACTOR_VERSION, "PRICE_BRIDGE_BAD_VERSION")
    _require(finality.get("verified") == 0 and
             finality.get("research_hold") is True and
             finality.get("production_writes") is False,
             "PRICE_BRIDGE_UNEXPECTED_SOURCE_CERTIFICATION")
    _require(venue.get("finality_verified") == 0 and
             venue.get("raw_and_yahoo_adjusted_directly_comparable") is False and
             venue.get("primary_session_asof_independently_certified") is False,
             "PRICE_BRIDGE_VENUE_FALSIFIED")
    _require(lineage.get("finality_verified") == 0 and
             lineage.get("independent_corporate_actions_certified") == 0 and
             lineage.get("required") == 25,
             "PRICE_BRIDGE_LINEAGE_FALSIFIED")
    source_rows = _objects_by_symbol(finality.get("symbols"), names, "SOURCE")
    venue_rows = _objects_by_symbol(venue.get("rows"), equities, "VENUE")
    factor_rows = _objects_by_symbol(lineage.get("rows"), equities, "YAHOO")
    rows = []
    for name in names:
        origin = source_rows[name]
        _require(origin.get("session") == session, "PRICE_BRIDGE_ROW_SESSION_MISMATCH")
        model_close = _price(origin.get("yahoo_close"), "MODEL_PRICE_INVALID")
        adjusted = origin.get("yahoo_is_adjusted")
        _require(type(adjusted) is bool and adjusted == (name != "^VIX"),
                 "PRICE_BRIDGE_MODEL_ADJUSTMENT_INVALID")
        row = {
            "symbol": name,
            "session": session,
            "group": "CORE_20" if name in spec["core"] else "CONTEXT_6",
            "model_input_auto_adjust_close": model_close,
            "model_input_adjusted": adjusted,
            "model_parquet_sha256": origin.get("source_parquet_sha256"),
            "raw_primary_M_auction_price": None,
            "vendor_unrepaired_split_adjusted_close": None,
            "vendor_unrepaired_dividend_adjusted_close": None,
            "vendor_unrepaired_adj_over_close": None,
            "vendor_trace_csv_sha256": None,
            "research_raw_M_minus_vendor_close_usd": None,
            "model_minus_vendor_adjusted_usd": None,
            "raw_reference_provenance": None,
            "reference_status": "UNAVAILABLE_HOLD",
            "vendor_trace_status": "NOT_APPLICABLE_VIX" if name == "^VIX" else "UNAVAILABLE_HOLD",
            "basis_reconciliation": "UNCOMPARABLE_WITHOUT_INDEPENDENT_FACTOR",
            "independent_price_certified": False,
            "independent_adjustment_factor_certified": False,
            "research_hold": True,
        }
        ref = origin.get("reference_price")
        if name == "^VIX":
            # Cboe publishes an unadjusted index. Do not fabricate a dividend
            # factor for it or count it as issuer adjustment certification.
            if ref is not None:
                row["reference_status"] = "VIX_PUBLISHED_RAW_REFERENCE_RESEARCH_ONLY"
                row["raw_reference_provenance"] = origin.get("reference_provider")
                row["raw_primary_M_auction_price"] = None
                row["basis_reconciliation"] = "VIX_INDEX_NO_CORPORATE_ACTION_FACTOR"
            rows.append(row)
            continue
        selected = venue_rows[name].get("selected_primary_raw_M_price")
        if selected is not None:
            raw_price = _price(selected, "VENUE_RAW_PRICE_INVALID")
            _require(ref is not None and
                     origin.get("reference_adjustment") == "RAW" and
                     origin.get("reference_type") == "REGULAR_CLOSE",
                     "PRIMARY_VENUE_REFERENCE_MISSING_OR_WRONG_BASIS")
            reference = _price(ref, "SOURCE_REFERENCE_INVALID")
            _require(abs(reference - raw_price) <= RAW_TOLERANCE,
                     "PRIMARY_VENUE_CROSS_REPORT_PRICE_CONFLICT")
            row["raw_primary_M_auction_price"] = raw_price
            row["reference_status"] = "PRIMARY_M_AUCTION_OBSERVED_NOT_FINALITY_CERTIFIED"
            row["raw_reference_provenance"] = {
                "provider": origin.get("reference_provider"),
                "feed": origin.get("reference_feed"),
                "exchange_code": venue_rows[name].get("selected_primary_venue_code"),
                "asset_metadata_sha256": venue_rows[name].get("asset_metadata_sha256"),
            }
        vendor = read_yahoo_trace(trace_dir, name, factor_rows[name], session)
        row["vendor_trace_status"] = vendor["status"]
        row["vendor_trace_csv_sha256"] = vendor.get("original_csv_sha256")
        if vendor["status"] == "YAHOO_VENDOR_TRACE_OBSERVED_UNCERTIFIED":
            close = vendor["vendor_close_split_adjusted"]
            adj = vendor["vendor_adj_close"]
            row["vendor_unrepaired_split_adjusted_close"] = close
            row["vendor_unrepaired_dividend_adjusted_close"] = adj
            row["vendor_unrepaired_adj_over_close"] = vendor["vendor_adj_over_vendor_close"]
            row["model_minus_vendor_adjusted_usd"] = round(model_close - adj, 8)
            if row["raw_primary_M_auction_price"] is not None:
                row["research_raw_M_minus_vendor_close_usd"] = round(
                    row["raw_primary_M_auction_price"] - close, 8)
                row["basis_reconciliation"] = "RAW_VS_VENDOR_SPLIT_BASIS_DIAGNOSTIC_ONLY"
            else:
                row["basis_reconciliation"] = "VENDOR_ONLY_NO_RAW_REFERENCE_HOLD"
            if abs(model_close - adj) > CENTS_TOLERANCE:
                row["basis_reconciliation"] += "_MODEL_REPAIR_DIFFERENCE_POSSIBLE"
        rows.append(row)

    _require(len(rows) == 26 and
             all(row["research_hold"] and not row["independent_price_certified"]
                 and not row["independent_adjustment_factor_certified"] for row in rows),
             "PRICE_BRIDGE_UNSUPPORTED_AUTO_CERTIFICATION")
    return {
        "version": VERSION, "session": session,
        "research_only": True, "live_execution": False,
        "production_writes": False, "strategy_promoted": False,
        "status": "PRICE_BASIS_RECONCILIATION_RESEARCH_HOLD",
        "raw_primary_M_auction_reference_count": sum(
            row["raw_primary_M_auction_price"] is not None for row in rows),
        "vendor_unrepaired_trace_count": sum(
            row["vendor_unrepaired_adj_over_close"] is not None for row in rows),
        "research_price_certified": 0, "required_assets": 26,
        "independent_adjustment_factors_certified": 0,
        "same_session_model_vendor_adj_close_mismatches_gt_half_cent": sum(
            row["model_minus_vendor_adjusted_usd"] is not None
            and abs(row["model_minus_vendor_adjusted_usd"]) > CENTS_TOLERANCE
            for row in rows),
        "limitations": [
            "SIP venue M print may not be certified consolidated session final close.",
            "Yahoo Close in historical API is split-adjusted, not authenticated raw SIP.",
            "Yahoo Adj Close and adjustment ratio have the same vendor provenance.",
            "Production can use repair=True; vendor trace is deliberately repair=False.",
            "Differences are research flags, never price corrections or orders.",
        ],
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="research/kalman_daily20/universe.json")
    parser.add_argument("--source-finality", required=True)
    parser.add_argument("--primary-venue", required=True)
    parser.add_argument("--yahoo-factor-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    spec = load_spec(args.config)
    finality = json.loads(Path(args.source_finality).read_text())
    venue = json.loads(Path(args.primary_venue).read_text())
    base = Path(args.yahoo_factor_dir)
    lineage = json.loads((base / "report.json").read_text())
    report = compare(spec, finality, venue, lineage, base)
    write_json(args.out, report)
    print(json.dumps({"DAILY20_PRICE_BASIS_BRIDGE": {
        "session": report["session"],
        "primary_M_raw_references": report["raw_primary_M_auction_reference_count"],
        "yahoo_unrepaired_traces": report["vendor_unrepaired_trace_count"],
        "model_vendor_mismatches_gt_half_cent":
            report["same_session_model_vendor_adj_close_mismatches_gt_half_cent"],
        "finality_verified": report["research_price_certified"],
        "status": report["status"],
    }}))


if __name__ == "__main__":
    main()
