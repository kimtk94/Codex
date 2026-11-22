#!/usr/bin/env python3
"""Read-only, same-session Daily20 price-variance research triage.

Categorize observed differences between a primary-venue SIP M print and
Yahoo's *split-adjusted* Close; the bases need not be equivalent. A price
difference is NOT a certified error, independent factor, or trade decision.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path

from daily20 import load_spec, write_json

VERSION = "daily20-price-variance-triage-v1"
BRIDGE_VERSION = "daily20-price-basis-bridge-v1"
HALF_CENT_USD = 0.005
BPS_10 = 10.0
BPS_50 = 50.0
BUCKETS = (
    "WITHIN_HALF_CENT_RESEARCH_ONLY",
    "OVER_HALF_CENT_UP_TO_10BPS",
    "OVER_10_UP_TO_50BPS",
    "OVER_50BPS_FACTOR_OR_VENUE_REVIEW",
    "RAW_OR_VENDOR_REFERENCE_MISSING_HOLD",
)
CSV_FIELDS = (
    "symbol", "session", "group", "classification", "review_priority",
    "raw_primary_M_usd", "yahoo_split_adjusted_close_usd",
    "yahoo_dividend_adjusted_close_usd", "model_input_close_usd",
    "raw_minus_yahoo_split_usd", "raw_minus_yahoo_split_bps",
    "yahoo_adj_over_split_close", "model_minus_yahoo_adjusted_usd",
    "venue", "raw_source_sha256", "vendor_trace_sha256",
    "model_parquet_sha256", "likely_cause_certified", "finality_verified",
)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def positive_or_none(v, *, field):
    if v is None:
        return None
    require(not isinstance(v, bool) and isinstance(v, (int, float)),
            field + "_NON_NUMERIC")
    val = float(v)
    require(math.isfinite(val) and val > 0, field + "_NOT_POSITIVE")
    return val


def valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(
        x in "0123456789abcdef" for x in value.lower())


def classify(raw, split):
    """Thresholds for *review queue only*, not same-basis certification."""
    if raw is None or split is None:
        return BUCKETS[4], "P0_MISSING_INPUT"
    delta = abs(raw - split)
    bps = delta / raw * 10000.0
    if delta <= HALF_CENT_USD:
        return BUCKETS[0], "P3_LOW_OBSERVED_DIFFERENCE"
    if bps <= BPS_10:
        return BUCKETS[1], "P2_AUCTION_OR_ROUNDING_REVIEW"
    if bps <= BPS_50:
        return BUCKETS[2], "P1_VENUE_AND_PRICE_BASIS_REVIEW"
    return BUCKETS[3], "P0_FACTOR_OR_VENUE_RECONCILIATION"


def build(spec, bridge, *, bridge_sha256):
    symbols = list(spec["core"]) + list(spec["context"])
    require(len(symbols) == 26 and len(set(symbols)) == 26
            and symbols.count("^VIX") == 1, "TRIAGE_CANONICAL_UNIVERSE_INVALID")
    require(bridge.get("version") == BRIDGE_VERSION, "TRIAGE_BRIDGE_VERSION_INVALID")
    require(bridge.get("required_assets") == 26
            and bridge.get("research_only") is True
            and bridge.get("production_writes") is False
            and bridge.get("strategy_promoted") is False
            and bridge.get("research_price_certified") == 0
            and bridge.get("independent_adjustment_factors_certified") == 0
            and bridge.get("status") == "PRICE_BASIS_RECONCILIATION_RESEARCH_HOLD",
            "TRIAGE_SOURCE_FALSE_CERTIFICATION")
    session = bridge.get("session")
    require(isinstance(session, str) and len(session) == 10,
            "TRIAGE_SOURCE_SESSION_INVALID")
    source = bridge.get("rows")
    require(isinstance(source, list) and len(source) == 26, "TRIAGE_SOURCE_ROWS_NOT_26")
    records = {}
    for item in source:
        require(isinstance(item, dict), "TRIAGE_SOURCE_ROW_INVALID")
        name = item.get("symbol")
        require(name in symbols and name not in records,
                "TRIAGE_DUPLICATE_OR_UNKNOWN_SYMBOL")
        require(item.get("session") == session and item.get("research_hold") is True
                and item.get("independent_price_certified") is False
                and item.get("independent_adjustment_factor_certified") is False,
                "TRIAGE_SOURCE_ROW_SCOPE_INVALID")
        expected_group = "CORE_20" if name in spec["core"] else "CONTEXT_6"
        require(item.get("group") == expected_group,
                "TRIAGE_SOURCE_ROW_GROUP_MISMATCH")
        require(valid_digest(item.get("model_parquet_sha256")),
                "TRIAGE_MODEL_PARQUET_SHA256_MISSING")
        records[name] = item
    require(set(records) == set(symbols), "TRIAGE_SYMBOL_COVERAGE_INVALID")

    index = records["^VIX"]
    require(index.get("model_input_adjusted") is False
            and index.get("raw_primary_M_auction_price") is None
            and index.get("vendor_unrepaired_adj_over_close") is None,
            "TRIAGE_VIX_SHOULD_NOT_HAVE_STOCK_FACTOR")
    equities = [s for s in symbols if s != "^VIX"]
    counters = {key: 0 for key in BUCKETS}
    cases = []
    for name in equities:
        r = records[name]
        require(r.get("model_input_adjusted") is True,
                "TRIAGE_EQUITY_NOT_ADJUSTED")
        model = positive_or_none(r.get("model_input_auto_adjust_close"), field="TRIAGE_MODEL")
        require(model is not None, "TRIAGE_MODEL_CLOSE_MISSING")
        raw = positive_or_none(r.get("raw_primary_M_auction_price"), field="TRIAGE_RAW")
        split = positive_or_none(
            r.get("vendor_unrepaired_split_adjusted_close"), field="TRIAGE_VENDOR_SPLIT")
        adj = positive_or_none(
            r.get("vendor_unrepaired_dividend_adjusted_close"), field="TRIAGE_VENDOR_ADJ")
        ratio = positive_or_none(r.get("vendor_unrepaired_adj_over_close"),
                                 field="TRIAGE_VENDOR_RATIO")
        if split is None:
            require(adj is None and ratio is None, "TRIAGE_VENDOR_PARTIAL_BASIS")
        else:
            require(adj is not None and ratio is not None
                    and math.isclose(adj / split, ratio, rel_tol=1e-8, abs_tol=1e-9),
                    "TRIAGE_VENDOR_RATIO_MISMATCH")
            require(valid_digest(r.get("vendor_trace_csv_sha256")),
                    "TRIAGE_VENDOR_TRACE_SHA256_MISSING")
        if raw is not None:
            provenance = r.get("raw_reference_provenance")
            require(isinstance(provenance, dict)
                    and provenance.get("provider") == "Alpaca"
                    and provenance.get("feed") == "SIP_MarketCenterOfficialClose_M"
                    and isinstance(provenance.get("exchange_code"), str)
                    and valid_digest(provenance.get("asset_metadata_sha256")),
                    "TRIAGE_PRIMARY_M_PROVENANCE_INCOMPLETE")
        bucket, priority = classify(raw, split)
        counters[bucket] += 1
        diff = raw - split if raw is not None and split is not None else None
        signed_bps = diff / raw * 10000.0 if diff is not None else None
        model_diff = model - adj if adj is not None else None
        cases.append({
            "symbol": name,
            "session": session,
            "group": "CORE_20" if name in spec["core"] else "CONTEXT_6",
            "classification": bucket,
            "review_priority": priority,
            "raw_primary_M_usd": raw,
            "yahoo_split_adjusted_close_usd": split,
            "yahoo_dividend_adjusted_close_usd": adj,
            "model_input_close_usd": model,
            "raw_minus_yahoo_split_usd": diff,
            "raw_minus_yahoo_split_bps": signed_bps,
            "yahoo_adj_over_split_close": ratio,
            "model_minus_yahoo_adjusted_usd": model_diff,
            "venue": (r["raw_reference_provenance"]["exchange_code"]
                      if raw is not None else None),
            "raw_source_sha256": (r["raw_reference_provenance"]["asset_metadata_sha256"]
                                  if raw is not None else None),
            "vendor_trace_sha256": (r.get("vendor_trace_csv_sha256")
                                   if split is not None else None),
            "model_parquet_sha256": r["model_parquet_sha256"],
            "likely_cause_certified": False,
            "finality_verified": False,
        })
    require(len(cases) == 25 and sum(counters.values()) == 25,
            "TRIAGE_RECONCILIATION_COUNT_INVALID")
    count_raw = sum(row["raw_primary_M_usd"] is not None for row in cases)
    count_vendor = sum(row["yahoo_split_adjusted_close_usd"] is not None
                       for row in cases)
    require(count_raw == bridge.get("raw_primary_M_auction_reference_count")
            and count_vendor == bridge.get("vendor_unrepaired_trace_count"),
            "TRIAGE_BRIDGE_COVERAGE_DIVERGED")
    mismatch_count = sum(
        row["model_minus_yahoo_adjusted_usd"] is not None
        and abs(row["model_minus_yahoo_adjusted_usd"]) > HALF_CENT_USD
        for row in cases)
    require(mismatch_count ==
            bridge.get("same_session_model_vendor_adj_close_mismatches_gt_half_cent"),
            "TRIAGE_BRIDGE_MODEL_DIFFERENCE_DIVERGED")

    # Deterministic rank; positive/negative direction retained in all cases.
    ordered = sorted(cases, key=lambda r: (
        r["raw_minus_yahoo_split_bps"] is None,
        -abs(r["raw_minus_yahoo_split_bps"] or 0),
        r["symbol"],
    ))
    return {
        "version": VERSION, "session": session,
        "research_only": True, "live_execution": False,
        "production_writes": False, "strategy_promoted": False,
        "status": "RAW_VS_SPLIT_ADJUSTED_DIAGNOSTIC_HOLD",
        "source_bridge_sha256": bridge_sha256,
        "required": 26, "equity_etf_cases": 25, "vix_index_separate": 1,
        "primary_M_research_references": count_raw,
        "yahoo_unrepaired_traces": count_vendor,
        "bucket_counts": counters,
        "model_yahoo_gt_half_cent": mismatch_count,
        "independent_final_close_certified": 0,
        "independent_factor_certified": 0,
        "strict_interpretation": (
            "Raw venue M and Yahoo split-adjusted Close are different "
            "price conventions. Buckets are *review priorities*, not proved "
            "provider errors, corporate-action causes, or certification."
        ),
        "top_10_abs_bps": [
            {"symbol": r["symbol"], "signed_bps": r["raw_minus_yahoo_split_bps"],
             "difference_usd": r["raw_minus_yahoo_split_usd"],
             "classification": r["classification"], "priority": r["review_priority"]}
            for r in ordered if r["raw_minus_yahoo_split_bps"] is not None
        ][:10],
        "review_queue": cases,
    }


def csv_payload(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: (row[key] if row[key] is not None else "")
                         for key in CSV_FIELDS})
    return out.getvalue().encode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="research/kalman_daily20/universe.json")
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    src = Path(args.bridge)
    blob = src.read_bytes()
    bridge = json.loads(blob)
    report = build(load_spec(args.config), bridge, bridge_sha256=sha256(blob).hexdigest())
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    review = csv_payload(report["review_queue"])
    (out / "review_queue.csv").write_bytes(review)
    report["review_queue_csv_sha256"] = sha256(review).hexdigest()
    write_json(out / "report.json", report)
    print(json.dumps({"DAILY20_PRICE_VARIANCE_TRIAGE": {
        "session": report["session"], "primary_M": report["primary_M_research_references"],
        "vendor_traces": report["yahoo_unrepaired_traces"],
        "buckets": report["bucket_counts"],
        "largest_8": report["top_10_abs_bps"][:8],
        "finality_verified": 0, "status": report["status"],
    }}))


if __name__ == "__main__":
    main()
