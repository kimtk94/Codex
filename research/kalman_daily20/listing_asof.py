#!/usr/bin/env python3
"""Historical primary-listing as-of evidence, kept separate from today's master.

Research-only. Never select a SIP market-center price or promote model finality
from this document; dates not explicitly covered by evidence are HOLD. Historical
listing source metadata cannot prove archived page bytes without their SHA256.
"""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse

from daily20 import load_spec, write_json

VERSION = "daily20-listing-asof-evidence-v1"
SOURCES_VERSION = "daily20-historical-listing-source-v1"
DEFAULT_SOURCES = Path("research/kalman_daily20/historical_listing_sources.json")
VENUE_TO_SIP = {"NYSE": "N", "NASDAQ": "Q", "NYSE_ARCA": "P"}
ALLOWED_HOSTS = {"www.sec.gov", "www.nasdaqtrader.com"}


def iso(value):
    if not isinstance(value, str):
        raise ValueError("LISTING_DATE_NOT_TEXT")
    d = date.fromisoformat(value)
    if d.isoformat() != value:
        raise ValueError("LISTING_DATE_NOT_ISO")
    return d


def validate(sources, universe):
    if sources.get("schema") != SOURCES_VERSION or sources.get("research_only") is not True:
        raise ValueError("LISTING_SOURCE_SCHEMA_OR_GOVERNANCE_INVALID")
    assets = [x for x in universe["core"] + universe["context"] if x != "^VIX"]
    if len(assets) != 25 or len(set(assets)) != 25:
        raise ValueError("LISTING_EXPECTS_25_EQUITIES_ETFS")
    docs = sources.get("sources")
    intervals = sources.get("intervals")
    if not isinstance(docs, list) or not isinstance(intervals, list):
        raise ValueError("LISTING_SOURCE_COLLECTION_INVALID")
    docs_by_id = {}
    for entry in docs:
        if not isinstance(entry, dict):
            raise ValueError("LISTING_DOCUMENT_OBJECT_REQUIRED")
        sid = entry.get("id")
        url = entry.get("url")
        if (not isinstance(sid, str) or not sid
                or sid in docs_by_id or not isinstance(url, str)):
            raise ValueError("LISTING_DOCUMENT_ID_OR_URL_INVALID")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError("LISTING_SOURCE_NOT_OFFICIAL_ALLOWLIST")
        if entry.get("actual_page_bytes_verified") is not False:
            raise ValueError("LISTING_PAGE_BYTES_NOT_ATTESTED")
        if entry.get("retrieved_page_sha256") is not None:
            raise ValueError("LISTING_UNVERIFIED_PAGE_DIGEST_FORBIDDEN")
        iso(entry["report_period_end"])
        docs_by_id[sid] = entry
    by_symbol = {symbol: [] for symbol in assets}
    for entry in intervals:
        if not isinstance(entry, dict):
            raise ValueError("LISTING_INTERVAL_NOT_OBJECT")
        sym = entry.get("symbol")
        if sym not in by_symbol:
            raise ValueError("LISTING_UNKNOWN_SYMBOL")
        start, end = iso(entry.get("from")), iso(entry.get("to_exclusive"))
        if start >= end:
            raise ValueError("LISTING_INVALID_INTERVAL")
        venue = entry.get("listing_venue")
        if VENUE_TO_SIP.get(venue) != entry.get("official_sip_code"):
            raise ValueError("LISTING_VENUE_SIP_CODE_MISMATCH")
        source_ids = entry.get("source_ids")
        if (not isinstance(source_ids, list) or not source_ids
                or len(source_ids) != len(set(source_ids))
                or any(id not in docs_by_id for id in source_ids)):
            raise ValueError("LISTING_MISSING_OFFICIAL_DOCUMENT")
        # Dates after a document's report-period end cannot be extrapolated,
        # even if the company's current listing happens to be unchanged.
        if not any(iso(docs_by_id[id]["report_period_end"]) >= end.fromordinal(end.toordinal()-1)
                   for id in source_ids):
            raise ValueError("LISTING_INTERVAL_BEYOND_SOURCE_PERIOD")
        by_symbol[sym].append({**entry, "from": start.isoformat(),
                              "to_exclusive": end.isoformat()})
    for symbol, records in by_symbol.items():
        records.sort(key=lambda v: v["from"])
        for prev, nxt in zip(records, records[1:]):
            if prev["to_exclusive"] > nxt["from"]:
                raise ValueError("LISTING_OVERLAPPING_VENUE_INTERVALS:" + symbol)
    return by_symbol, docs_by_id, assets


def lookup(by_symbol, docs_by_id, symbol, day):
    query = iso(day)
    matches = [
        row for row in by_symbol[symbol]
        if iso(row["from"]) <= query < iso(row["to_exclusive"])
    ]
    if len(matches) != 1:
        return {"status": "NO_DATED_LISTING_EVIDENCE_HOLD",
                "symbol": symbol, "session": day, "venue": None, "sip_code": None,
                "asof_certified": False}
    item = matches[0]
    return {
        "status": "HISTORIC_LISTING_DOCUMENTED_RESEARCH_ONLY",
        "symbol": symbol, "session": day,
        "venue": item["listing_venue"], "sip_code": item["official_sip_code"],
        "interval_from": item["from"], "interval_to_exclusive": item["to_exclusive"],
        "source_ids": item["source_ids"],
        "source_urls": [docs_by_id[id]["url"] for id in item["source_ids"]],
        "page_bytes_independently_archived": False,
        "asof_certified": False,
    }


def audit(spec, sources, session, *, venue_reference=None):
    iso(session)
    by_symbol, docs, assets = validate(sources, spec)
    current_rows = {}
    if venue_reference is not None:
        if (venue_reference.get("session") != session
                or venue_reference.get("tested_assets") != 25
                or venue_reference.get("finality_verified") != 0):
            raise ValueError("LISTING_CURRENT_VENUE_REPORT_INVALID")
        rows = venue_reference.get("rows", [])
        if not isinstance(rows, list) or len(rows) != 25:
            raise ValueError("LISTING_CURRENT_VENUE_ROWS_INVALID")
        current_rows = {item["symbol"]: item for item in rows}
        if set(current_rows) != set(assets):
            raise ValueError("LISTING_CURRENT_VENUE_SET_MISMATCH")
    rows = []
    for symbol in assets:
        result = lookup(by_symbol, docs, symbol, session)
        if symbol in current_rows:
            result["provider_current_master_exchange"] = current_rows[symbol].get("asset_exchange")
            result["provider_current_master_is_historical_evidence"] = False
            result["current_master_venue_selected_raw"] = current_rows[symbol].get(
                "selected_primary_venue_code")
            result["current_raw_m_price_certified"] = False
        rows.append(result)
    regressions = [
        lookup(by_symbol, docs, "PLTR", "2024-11-25"),
        lookup(by_symbol, docs, "PLTR", "2024-11-26"),
    ]
    if (regressions[0]["sip_code"] != "N" or regressions[1]["sip_code"] != "Q"):
        raise ValueError("LISTING_PLTR_HISTORICAL_MIGRATION_REGRESSION_FAILED")
    return {
        "version": VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "finality_verified": 0,
        "historical_listing_asof_certified": 0, "required": 25,
        "asof_research_interval_covered": sum(
            x["status"] == "HISTORIC_LISTING_DOCUMENTED_RESEARCH_ONLY"
            for x in rows),
        "source_provenance_status": "OFFICIAL_DOCUMENT_URLS_NO_CAPTURED_SOURCE_BYTES",
        "documented_historical_symbols": sum(bool(v) for v in by_symbol.values()),
        "documented_historical_intervals": sum(len(v) for v in by_symbol.values()),
        "sources_manifest_sha256": sha256(json.dumps(
            sources,sort_keys=True,ensure_ascii=False,
            separators=(",",":")).encode()).hexdigest(),
        "status": "HISTORICAL_LISTING_ASOF_RESEARCH_HOLD",
        "rows": rows,
        "pltr_transfer_regression": regressions,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--sources", default=str(DEFAULT_SOURCES))
    p.add_argument("--qc", required=True)
    p.add_argument("--current-venue")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    qc=json.loads(Path(args.qc).read_text())
    if qc.get("ready") != 26 or qc.get("status") != "READY":
        raise ValueError("LISTING_REQUIRES_26_READY_QC")
    result = audit(load_spec(args.config), json.loads(Path(args.sources).read_text()),
                   qc["expected_session"],
                   venue_reference=(json.loads(Path(args.current_venue).read_text())
                                    if args.current_venue else None))
    write_json(args.out, result)
    print("DAILY20_HISTORICAL_LISTING", result["asof_research_interval_covered"],
          "/25 ASOF DOCUMENTED; PLTR 2024-11-25 N / 2024-11-26 Q;",
          "CERTIFIED 0/25 HOLD")


if __name__ == "__main__":
    main()
