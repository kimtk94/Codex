#!/usr/bin/env python3
"""Fail-closed, read-only evidence obligations for all 26 Daily20 instruments.

A SIP market-center M print is not a consolidated exchange-certified close.
Yahoo Close/Adj Close and any same-vendor ratio are not an independent factor.
Never infer certification, a price correction, or model promotion from agreement.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

VERSION = "daily20-26asset-official-proof-obligations-v1"
EXPECTED = {
    "source": "daily20-source-finality-v1",
    "bridge": "daily20-price-basis-bridge-v1",
    "actions": "daily20-corporate-action-crosscheck-v1",
    "gaps": "daily20-issuer-ca-gap-audit-v1",
}
CSV_FIELDS = [
    "symbol", "session", "group", "asset_type", "close_reference_grade",
    "primary_M_observed", "vendor_trace_observed", "action_crosscheck_status",
    "issuer_cash_gap", "close_certified", "factor_certified",
    "required_evidence", "status", "model_parquet_sha256",
]


def require(condition, code):
    if not condition:
        raise ValueError(code)


def indexed(rows, expected, label):
    require(isinstance(rows, list) and len(rows) == len(expected),
            label + "_COVERAGE_COUNT_MISMATCH")
    out = {}
    for row in rows:
        require(isinstance(row, dict), label + "_INVALID_ROW")
        symbol = row.get("symbol")
        require(symbol in expected and symbol not in out,
                label + "_DUPLICATE_OR_UNKNOWN_SYMBOL")
        out[symbol] = row
    require(set(out) == set(expected), label + "_MISSING_SYMBOL")
    return out


def build(spec, source, bridge, actions, gaps, *, input_sha256):
    symbols = list(spec["core"]) + list(spec["context"])
    equities = [s for s in symbols if s != "^VIX"]
    require(len(spec["core"]) == 20 and len(spec["context"]) == 6
            and len(symbols) == len(set(symbols)) == 26
            and len(equities) == 25 and symbols.count("^VIX") == 1,
            "PROOF_CANONICAL_20_PLUS_6_REQUIRED")
    for name, doc in (("source", source), ("bridge", bridge),
                      ("actions", actions), ("gaps", gaps)):
        require(doc.get("version") == EXPECTED[name], "PROOF_VERSION_" + name)
        require(doc.get("research_only") is True
                and doc.get("production_writes") is False
                and doc.get("strategy_promoted") is False,
                "PROOF_UPSTREAM_SCOPE_" + name)
    session = source.get("session")
    require(isinstance(session, str) and len(session) == 10
            and session == bridge.get("session") == actions.get("session"),
            "PROOF_SOURCE_SESSION_MISMATCH")
    require(source.get("research_hold") is True
            and source.get("verified") == 0
            and source.get("required") == 26
            and source.get("external_regular_close_independent_certified") is False,
            "PROOF_SOURCE_FALSE_CERTIFICATION")
    require(bridge.get("research_price_certified") == 0
            and bridge.get("independent_adjustment_factors_certified") == 0
            and bridge.get("required_assets") == 26,
            "PROOF_BRIDGE_FALSE_CERTIFICATION")
    require(actions.get("finality_verified") == 0
            and actions.get("independent_factor_certification") == 0
            and actions.get("required") == 25,
            "PROOF_CA_FALSE_CERTIFICATION")
    require(gaps.get("issuer_payments_certified") == 0
            and gaps.get("source_finality_verified") == 0
            and gaps.get("status") == "ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD",
            "PROOF_ISSUER_FALSE_CERTIFICATION")
    srows = indexed(source.get("symbols"), symbols, "PROOF_FINALITY")
    brows = indexed(bridge.get("rows"), symbols, "PROOF_BRIDGE")
    arows = indexed(actions.get("symbols"), equities, "PROOF_ACTION")
    gap_rows = gaps.get("events")
    require(isinstance(gap_rows, list) and len(gap_rows) == 2,
            "PROOF_ISSUER_TWO_EVENTS_REQUIRED")
    issuer_gaps = {}
    for event in gap_rows:
        require(isinstance(event, dict), "PROOF_ISSUER_BAD_EVENT")
        target = (event.get("symbol"), event.get("ex_date"))
        require(target in {("QQQ", "2018-06-18"), ("QLD", "2023-09-20")}
                and target not in issuer_gaps
                and event.get("actual_payment_certified") is False
                and event.get("independent_adjustment_factor_certified") is False
                and event.get("independent_close_certified") is False
                and event.get("research_hold") is True,
                "PROOF_ISSUER_EVENT_UNVERIFIED_OR_INVALID")
        issuer_gaps[target] = event
    require(len(issuer_gaps) == 2, "PROOF_ISSUER_EVENT_MISSING")

    result = []
    for symbol in symbols:
        s = srows[symbol]
        b = brows[symbol]
        require(s.get("session") == b.get("session") == session
                and s.get("reference_certified") is False
                and s.get("finality_verified") is False
                and b.get("research_hold") is True
                and b.get("independent_price_certified") is False
                and b.get("independent_adjustment_factor_certified") is False
                and b.get("model_parquet_sha256") == s.get("source_parquet_sha256")
                and isinstance(b.get("model_parquet_sha256"), str)
                and len(b["model_parquet_sha256"]) == 64,
                "PROOF_ROW_IDENTITY_OR_UNSUPPORTED_FINALITY_" + symbol)
        is_index = symbol == "^VIX"
        expected_group = "CORE_20" if symbol in spec["core"] else "CONTEXT_6"
        require(b.get("group") == s.get("group") == expected_group,
                "PROOF_GROUP_MISMATCH_" + symbol)
        if is_index:
            require(b.get("raw_primary_M_auction_price") is None
                    and b.get("vendor_unrepaired_adj_over_close") is None
                    and b.get("model_input_adjusted") is False,
                    "PROOF_VIX_STOCK_ADJUSTMENT_FORBIDDEN")
            observed = s.get("reference_price") is not None
            grade = ("CBOE_INDEX_PUBLICATION_UNCERTIFIED" if observed
                     and s.get("reference_provider") == "Cboe"
                     else "CBOE_INDEX_PROOF_MISSING_HOLD")
            obligations = ["CBOE_AUTHENTICATED_SESSION_VALUE_AND_VINTAGE",
                           "INDEPENDENT_AS_OF_REPLAY_CONSISTENCY"]
            action_status = "NOT_APPLICABLE_VIX_INDEX"
            factor_certified = None
        else:
            a = arows[symbol]
            require(a.get("factor_independently_certified") is False,
                    "PROOF_CA_ROW_FALSE_ATTESTATION_" + symbol)
            require(b.get("model_input_adjusted") is True,
                    "PROOF_EQUITY_BASIS_INVALID_" + symbol)
            observed = b.get("raw_primary_M_auction_price") is not None
            grade = ("SIP_PRIMARY_M_RESEARCH_REFERENCE_ONLY" if observed
                     else "PRIMARY_M_NOT_OBSERVED_HOLD")
            obligations = [
                "CERTIFIED_XNYS_SCHEDULED_REGULAR_CLOSE_NOT_JUST_M_PRINT",
                "POINT_IN_TIME_PRIMARY_LISTING_VENUE",
                "ISSUER_VERIFIED_SPLIT_AND_CASH_DISTRIBUTION_FACTOR_CHAIN",
                "YAHOO_REPAIR_AND_VINTAGE_BRIDGE_RECONCILIATION",
            ]
            action_status = a.get("status", "CA_REPORT_STATUS_UNAVAILABLE_HOLD")
            factor_certified = False
        issuer_day = {"QQQ": "2018-06-18", "QLD": "2023-09-20"}.get(symbol)
        if issuer_day:
            obligations.append("FIRST_PARTY_EX_DATE_CASH_AMOUNT_SHARE_UNIT_" + issuer_day)
        result.append({
            "symbol": symbol, "session": session, "group": expected_group,
            "asset_type": "CBOE_INDEX" if is_index else "EQUITY_OR_ETF",
            "close_reference_grade": grade,
            "primary_M_observed": bool(observed) if not is_index else False,
            "vendor_trace_observed": (b.get("vendor_unrepaired_adj_over_close")
                                      is not None) if not is_index else False,
            "action_crosscheck_status": action_status,
            "issuer_cash_gap": issuer_day,
            "close_certified": False,
            "factor_certified": factor_certified,
            "required_evidence": obligations,
            "status": "OFFICIAL_CLOSE_AND_FACTOR_RESEARCH_HOLD",
            "model_parquet_sha256": b["model_parquet_sha256"],
        })
    require(len(result) == 26
            and sum(row["factor_certified"] is False for row in result) == 25,
            "PROOF_OUTPUT_COUNT_INVALID")
    return {
        "version": VERSION, "session": session,
        "research_only": True, "live_execution": False,
        "production_writes": False, "strategy_promoted": False,
        "status": "OFFICIAL_CLOSE_AND_FACTOR_RESEARCH_HOLD",
        "required_assets": 26, "equity_etf_assets": 25, "index_assets": 1,
        "official_close_certified": 0, "independent_factor_certified": 0,
        "independent_factor_applicable": 25,
        "issuer_specific_cash_gaps": 2,
        "primary_M_observed": sum(x["primary_M_observed"] for x in result),
        "vendor_traces_observed": sum(x["vendor_trace_observed"] for x in result),
        "input_sha256": dict(input_sha256), "rows": result,
    }


def run(config, source, bridge, actions, gaps, out_dir):
    paths = dict(config=config, source=source, bridge=bridge,
                 actions=actions, gaps=gaps)
    raw = {name: Path(path).read_bytes() for name, path in paths.items()}
    docs = {name: json.loads(payload) for name, payload in raw.items()}
    hashes = {name: sha256(payload).hexdigest() for name, payload in raw.items()}
    report = build(docs["config"], docs["source"], docs["bridge"],
                   docs["actions"], docs["gaps"], input_sha256=hashes)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    table = target / "evidence_obligations.csv"
    with table.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({
                **row,
                "required_evidence": ";".join(row["required_evidence"]),
            })
    report["evidence_obligations_csv_sha256"] = sha256(table.read_bytes()).hexdigest()
    (target / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--source", required=True)
    p.add_argument("--bridge", required=True)
    p.add_argument("--actions", required=True)
    p.add_argument("--gaps", required=True)
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()
    r = run(args.config, args.source, args.bridge, args.actions, args.gaps, args.out_dir)
    print("DAILY20_26_PRICE_FACTOR_PROOF_HOLD", r["session"],
          "M research refs", r["primary_M_observed"], "/25",
          "official closes", r["official_close_certified"], "/26",
          "independent factors", r["independent_factor_certified"], "/25",
          "issuer cash gaps", r["issuer_specific_cash_gaps"])


if __name__ == "__main__":
    main()
