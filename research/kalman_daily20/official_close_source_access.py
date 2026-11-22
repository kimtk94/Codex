#!/usr/bin/env python3
"""Audit primary-publisher close access paths without certifying vendor quotes.

Only Cboe's freely published VIX CSV is fetched again on protected main.
NYSE TAQ/Arca, Nasdaq NOCP, and Cboe BZX feeds are documented procurement
routes, not guessed publicly available prices. All 26 remain research HOLD.
"""
from __future__ import annotations

import argparse
from datetime import date
import gzip
from hashlib import sha256
import json
from pathlib import Path

from collect_independent_close import (
    CBOE_URL, MAX_CBOE_BYTES, http_bytes, parse_cboe_csv,
)

VERSION = "daily20-primary-publisher-access-v1"
ROUTES = {
    "NASDAQ": {
        "publisher": "Nasdaq",
        "product": "Nasdaq Official Closing Price (NOCP)",
        "documentation": "https://www.nasdaq.com/market-activity/quotes/historical-nocp",
        "access_status": "AUTHENTICATED_SESSION_NUMERIC_RECORD_NOT_CONNECTED_HOLD",
    },
    "NYSE": {
        "publisher": "NYSE",
        "product": "TAQ Closing Prices",
        "documentation": "https://www.nyse.com/data-products/catalog/taq-nyse-closing-prices",
        "access_status": "LICENSED_DAILY_FILE_NOT_CONFIGURED_HOLD",
    },
    "NYSE_ARCA": {
        "publisher": "NYSE Arca",
        "product": "TAQ Closing Prices",
        "documentation": "https://www.nyse.com/data-products/catalog/taq-nyse-closing-prices",
        "access_status": "LICENSED_DAILY_FILE_NOT_CONFIGURED_HOLD",
    },
    "NYSE_AMERICAN": {
        "publisher": "NYSE American",
        "product": "TAQ Closing Prices",
        "documentation": "https://www.nyse.com/data-products/catalog/taq-nyse-closing-prices",
        "access_status": "LICENSED_DAILY_FILE_NOT_CONFIGURED_HOLD",
    },
    "CBOE_BZX": {
        "publisher": "Cboe BZX",
        "product": "BZX Closing Auction Summary",
        "documentation": "https://www.cboe.com/markets/us/equities/market-statistics/auction",
        "access_status": "HISTORIC_PRIMARY_BZX_CLOSE_NOT_CONFIGURED_HOLD",
    },
}
INDEX_URL = "https://www.cboe.com/tradable_products/vix/vix_historical_data"


def require(ok, code):
    if not ok:
        raise ValueError(code)


def unique_rows(doc, names, key):
    rows = doc.get(key)
    require(isinstance(rows, list) and len(rows) == len(names),
            "ACCESS_" + key.upper() + "_COUNT")
    result = {}
    for row in rows:
        require(isinstance(row, dict), "ACCESS_ROW_INVALID")
        symbol = row.get("symbol")
        require(symbol in names and symbol not in result,
                "ACCESS_UNKNOWN_OR_DUPLICATE_SYMBOL")
        result[symbol] = row
    require(set(result) == set(names), "ACCESS_ASSET_MISSING")
    return result


def recheck_cboe(original, reference, session, *, raw=None, attempted=False):
    """Compare two Cboe captures by dated value, not whole mutable CSV hash.

    Cboe appends new sessions to its public file, so differences in SHA256 do
    not necessarily imply a revision of an already published closing value.
    """
    previous = original.get("cboe", {})
    require(isinstance(previous, dict), "ACCESS_CBOE_ORIGINAL_SCHEMA")
    quotes = reference.get("quotes")
    require(isinstance(quotes, list), "ACCESS_CBOE_QUOTES_SCHEMA")
    candidates = [x for x in quotes if x.get("symbol") == "^VIX"]
    require(len(candidates) <= 1, "ACCESS_CBOE_REFERENCE_DUPLICATE")
    row = candidates[0] if candidates else None
    published = previous.get("status") == "CBOE_OFFICIAL_VIX_HISTORY_PRESENT"
    if published:
        require(previous.get("provider") == "Cboe"
                and previous.get("index_admin_publication") is True
                and isinstance(previous.get("body_sha256"), str)
                and len(previous["body_sha256"]) == 64
                and row is not None
                and row.get("provider") == "Cboe"
                and row.get("feed") == "VIX_Index_Historical_Daily_Close"
                and row.get("source_url") == CBOE_URL
                and row.get("source_body_sha256") == previous["body_sha256"]
                and row.get("quote_type") == "REGULAR_CLOSE"
                and row.get("adjustment") == "RAW"
                and row.get("independently_exchange_certified_at_16_00") is False
                and float(row["price"]) == float(previous["official_index_close"]),
                "ACCESS_CBOE_ANCHOR_CONFLICT")
    elif row is not None:
        raise ValueError("ACCESS_CBOE_UNSUPPORTED_QUOTE_WITHOUT_PUBLICATION")

    evidence = {
        "publisher": "Cboe",
        "official_index_history_page": INDEX_URL,
        "official_index_csv_url": CBOE_URL,
        "original_publisher_observed": published,
        "original_response_sha256": previous.get("body_sha256"),
        "original_close": previous.get("official_index_close") if published else None,
        "recheck_attempted": attempted,
        "recheck_raw_sha256": None,
        "recheck_close": None,
        "same_session_value_unchanged": None,
        "recheck_status": "CBOE_RECHECK_NOT_RUN_OFFLINE_HOLD",
        "official_16_et_clock_certified": False,
        "asset_finality_certified": False,
    }
    if not attempted:
        require(raw is None, "ACCESS_OFFLINE_RAW_NOT_ALLOWED")
        return evidence
    if raw is None:
        evidence["recheck_status"] = "CBOE_RECHECK_NETWORK_UNAVAILABLE_HOLD"
        return evidence
    require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_CBOE_BYTES,
            "ACCESS_CBOE_BAD_BODY_SIZE")
    checked = parse_cboe_csv(raw, session)
    evidence["recheck_raw_sha256"] = checked["body_sha256"]
    evidence["recheck_close"] = checked["close"]
    evidence["latest_published_session"] = checked["latest_published_session"]
    if checked["close"] is None or not published:
        evidence["recheck_status"] = "CBOE_SESSION_OR_ORIGINAL_MISSING_HOLD"
    else:
        same = abs(float(checked["close"]) - float(previous["official_index_close"])) <= 1e-8
        evidence["same_session_value_unchanged"] = same
        evidence["recheck_status"] = (
            "CBOE_TWO_CAPTURES_MATCH_PUBLISHER_ONLY_HOLD"
            if same else "CBOE_HISTORICAL_PUBLISHER_REVISION_HOLD")
    return evidence


def build(spec, original, reference, venue, obligations, *,
          input_sha256, cboe_raw=None, recheck_attempted=False):
    names = list(spec["core"]) + list(spec["context"])
    equities = [x for x in names if x != "^VIX"]
    require(len(spec["core"]) == 20 and len(spec["context"]) == 6
            and len(set(names)) == len(names) == 26
            and len(equities) == 25, "ACCESS_NOT_20_6")
    session = original.get("session")
    require(isinstance(session, str) and session == reference.get("session")
            == venue.get("session") == obligations.get("session"),
            "ACCESS_SESSION_CONFLICT")
    date.fromisoformat(session)
    require(original.get("version") == "daily20-independent-feed-diagnostics-v1"
            and reference.get("schema") == "daily20-quote-reference-v1"
            and venue.get("version") == "daily20-primary-listing-evidence-v1"
            and obligations.get("version") == "daily20-26asset-official-proof-obligations-v1",
            "ACCESS_UPSTREAM_VERSION")
    require(original.get("research_only") is True
            and venue.get("research_only") is True
            and obligations.get("research_only") is True
            and original.get("verified_regular_finality") == 0
            and venue.get("finality_verified") == 0
            and obligations.get("official_close_certified") == 0
            and obligations.get("independent_factor_certified") == 0
            and obligations.get("required_assets") == 26
            and original.get("production_writes") is False
            and venue.get("production_writes") is False
            and obligations.get("production_writes") is False,
            "ACCESS_FALSE_FINALITY_UPSTREAM")
    vs = unique_rows(venue, equities, "rows")
    os = unique_rows(obligations, names, "rows")
    for symbol in names:
        require(os[symbol].get("session") == session
                and os[symbol].get("close_certified") is False
                and os[symbol].get("status") == "OFFICIAL_CLOSE_AND_FACTOR_RESEARCH_HOLD",
                "ACCESS_OBLIGATION_FALSE_CERTIFICATION")
    stamp = recheck_cboe(original, reference, session,
                         raw=cboe_raw, attempted=recheck_attempted)
    rows = []
    for symbol in names:
        if symbol == "^VIX":
            rows.append({
                "symbol": symbol, "asset_type": "INDEX",
                "session": session, "current_listed_venue": "CBOE_INDEX_ADMIN",
                "publisher": "Cboe", "official_product": "VIX Historical Daily Close",
                "source_url": CBOE_URL,
                "access_status": stamp["recheck_status"],
                "official_close_record_attached": bool(stamp["original_publisher_observed"]),
                "independently_licensed_final_close_attached": False,
                "session_listing_identity_certified": None,
                "point_in_time_close_certified": False,
                "corporate_factor_applicable": False,
                "production_writes": False,
            })
            continue
        prior = vs[symbol]
        canonical = prior.get("primary_canonical")
        route = ROUTES.get(canonical)
        # Current Alpaca master is a routing clue, NEVER historical proof.
        if route is None:
            route = {
                "publisher": None, "product": None, "documentation": None,
                "access_status": "UNKNOWN_CURRENT_PRIMARY_VENUE_HOLD",
            }
        require(prior.get("session") == session
                and prior.get("session_primary_listing_certified") is False
                and prior.get("primary_market_center_M_certified_as_consolidated_close") is False
                and prior.get("direct_comparison_with_Yahoo_auto_adjust") is False
                and os[symbol].get("primary_M_observed") is
                (prior.get("selected_primary_raw_M_price") is not None),
                "ACCESS_VENUE_REFERENCE_CONFLICT")
        rows.append({
            "symbol": symbol, "asset_type": "EQUITY_OR_ETF",
            "session": session, "current_listed_venue": canonical,
            "publisher": route["publisher"], "official_product": route["product"],
            "source_url": route["documentation"],
            "access_status": route["access_status"],
            "official_close_record_attached": False,
            "independently_licensed_final_close_attached": False,
            "session_listing_identity_certified": False,
            "point_in_time_close_certified": False,
            "corporate_factor_applicable": True,
            "production_writes": False,
        })
    return {
        "version": VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "live_execution": False,
        "status": "PRIMARY_PUBLISHER_ACCESS_AND_CERTIFICATION_RESEARCH_HOLD",
        "official_close_certified": 0, "official_close_required": 26,
        "independent_corporate_factors_certified": 0,
        "equities_missing_primary_numeric_evidence": 25,
        "cboe_publisher_recheck": stamp,
        "access_route_counts": {
            k: sum(x["current_listed_venue"] == k for x in rows)
            for k in sorted(set(x["current_listed_venue"] for x in rows if x["symbol"] != "^VIX"))
        },
        "input_sha256": dict(input_sha256),
        "rows": rows,
        "disclosure": (
            "A publisher URL, a current venue assignment, an Alpaca M print, "
            "or two matches from the SAME Cboe source cannot independently "
            "certify a 16:00 point-in-time trade close or a vendor adjustment."
        ),
    }


def run(config, independent, reference, venue, obligations, out_dir,
        *, probe_cboe=False, fetcher=http_bytes):
    paths = {"config": config, "independent": independent,
             "reference": reference, "venue": venue, "obligations": obligations}
    raw = {name: Path(path).read_bytes() for name, path in paths.items()}
    docs = {name: json.loads(data) for name, data in raw.items()}
    hashes = {name: sha256(data).hexdigest() for name, data in raw.items()}
    cboe_raw = None
    if probe_cboe:
        try:
            cboe_raw = fetcher(CBOE_URL, {"Accept": "text/csv"}, limit=MAX_CBOE_BYTES)
        except (OSError, RuntimeError, TimeoutError):
            cboe_raw = None
    report = build(docs["config"], docs["independent"], docs["reference"],
                   docs["venue"], docs["obligations"], input_sha256=hashes,
                   cboe_raw=cboe_raw, recheck_attempted=probe_cboe)
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    if cboe_raw is not None:
        # Public publisher bytes only, never an Alpaca/licensed vendor feed.
        with (base / "cboe_vix_public_source.csv.gz").open("wb") as stream:
            with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as handle:
                handle.write(cboe_raw)
        report["raw_publication_gzip_sha256"] = sha256(
            (base / "cboe_vix_public_source.csv.gz").read_bytes()).hexdigest()
    (base / "report.json").write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--independent", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--venue", required=True)
    p.add_argument("--obligations", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--probe-cboe", action="store_true")
    args = p.parse_args()
    r = run(args.config, args.independent, args.reference, args.venue,
            args.obligations, args.out_dir, probe_cboe=args.probe_cboe)
    print("DAILY20_PRIMARY_SOURCE_ACCESS_HOLD", r["session"],
          "routes", r["access_route_counts"],
          "Cboe", r["cboe_publisher_recheck"]["recheck_status"],
          "OFFICIAL CERTIFIED", r["official_close_certified"], "/26")


if __name__ == "__main__":
    main()
