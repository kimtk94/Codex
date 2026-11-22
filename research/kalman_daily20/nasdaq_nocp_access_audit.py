#!/usr/bin/env python3
"""Research-only Nasdaq NOCP access diagnostics, never an execution price source.

Nasdaq Historical NOCP browser pages are not authenticated dated records.
The licensed Fundamental Data T+1 report lists NOCP separately from daily last
sale. This probe records page access/bytes SHA only; never scrapes prices.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor

VERSION = "daily20-nasdaq-nocp-public-access-v1"
SOURCE_VERSION = "daily20-primary-publisher-access-v1"
FUNDAMENTAL_URL = "https://nasdaqtrader.com/Trader.aspx?id=FD"
NBPL_URL = "https://data.nasdaq.com/databases/NBPL"
NASDAQ_URL = "https://www.nasdaq.com/market-activity"
MAX_RESPONSE_BYTES = 2_000_000
ETF_SYMBOLS = frozenset(("SPY", "QQQ", "QLD", "IWM", "SMH",
                         "HYG", "LQD", "TLT", "GLD"))
CSV_FIELDS = ("symbol", "session", "page_url", "probe_attempted", "http_status",
              "probe_status", "response_sha256", "response_bytes",
              "html_unavailable_placeholder", "nocp_price", "official_certified")


def require(condition, code):
    if not condition:
        raise ValueError(code)


def digest_ok(value):
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value.lower()
    )


def page_url(symbol):
    require(isinstance(symbol, str) and symbol.isascii()
            and 1 <= len(symbol) <= 8 and symbol.isalnum()
            and symbol == symbol.upper(), "NOCP_UNSAFE_SYMBOL")
    category = "etf" if symbol in ETF_SYMBOLS else "stocks"
    return f"{NASDAQ_URL}/{category}/{symbol.lower()}/historical-nocp"


def public_http_probe(url):
    """One strictly bounded, unauthenticated publisher HTML GET.

    Never send account details, follow a third-party redirect, or parse a
    price from a page with dynamic JavaScript elements.
    """
    require(url.startswith(NASDAQ_URL + "/"), "NOCP_UNEXPECTED_PROBE_URL")
    req = Request(url, headers={
        "User-Agent": "Kalman-Daily20-Publisher-Page-Research/1.0",
        "Accept": "text/html",
    })
    try:
        with urlopen(req, timeout=10) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != "www.nasdaq.com":
                return {"probe_status": "NASDAQ_REDIRECT_OUTSIDE_PUBLISHER_HOLD",
                        "http_status": None, "response_sha256": None,
                        "response_bytes": None, "html_unavailable_placeholder": None}
            status = response.status
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES or not body:
                return {"probe_status": "NASDAQ_HTML_OVERSIZE_OR_EMPTY_HOLD",
                        "http_status": status, "response_sha256": None,
                        "response_bytes": len(body),
                        "html_unavailable_placeholder": None}
            return classify_html(body, status)
    except HTTPError as exc:
        return {"probe_status": "NASDAQ_HTTP_" + str(exc.code) + "_HOLD",
                "http_status": exc.code, "response_sha256": None,
                "response_bytes": None, "html_unavailable_placeholder": None}
    except (URLError, OSError, TimeoutError) as exc:
        return {"probe_status": "NASDAQ_FETCH_" + type(exc).__name__ + "_HOLD",
                "http_status": None, "response_sha256": None,
                "response_bytes": None, "html_unavailable_placeholder": None}


def classify_html(body, status):
    """HTML does not fulfill a dated authenticated NOCP numeric contract."""
    require(isinstance(body, bytes) and 0 < len(body) <= MAX_RESPONSE_BYTES,
            "NOCP_INVALID_HTML_BYTES")
    require(isinstance(status, int) and 200 <= status <= 299,
            "NOCP_INVALID_HTML_STATUS")
    decoded = body.decode("utf-8", errors="replace")
    marker = "historical nocp" in decoded.lower()
    placeholder = "data is currently not available" in decoded.lower()
    classification = (
        "NASDAQ_HISTORICAL_NOCP_HTML_NOT_AUTHENTICATED_NUMERIC_HOLD"
        if marker else "NASDAQ_PAGE_WITHOUT_NOCP_IDENTITY_HOLD"
    )
    return {
        "probe_status": classification,
        "http_status": status,
        "response_sha256": sha256(body).hexdigest(),
        "response_bytes": len(body),
        "html_unavailable_placeholder": placeholder,
    }


def build(spec, access, *, probes, probe_attempted, file_hashes,
          fetched_at=None):
    require(spec.get("research_only") is True
            and access.get("version") == SOURCE_VERSION
            and access.get("research_only") is True
            and access.get("production_writes") is False
            and access.get("strategy_promoted") is False
            and access.get("live_execution") is False
            and access.get("official_close_certified") == 0
            and access.get("official_close_required") == 26
            and access.get("independent_corporate_factors_certified") == 0
            and access.get("equities_missing_primary_numeric_evidence") == 25,
            "NOCP_UPSTREAM_RESEARCH_SCOPE_VIOLATION")
    names = list(spec.get("core", [])) + list(spec.get("context", []))
    require(len(spec.get("core", [])) == 20
            and len(spec.get("context", [])) == 6
            and len(set(names)) == len(names) == 26
            and "^VIX" in names, "NOCP_CANONICAL_26_INVALID")
    session = access.get("session")
    require(isinstance(session, str), "NOCP_SESSION_MISSING")
    date.fromisoformat(session)
    source = access.get("rows")
    require(isinstance(source, list) and len(source) == 26,
            "NOCP_UPSTREAM_26_ROWS_REQUIRED")
    by_symbol = {}
    for row in source:
        require(isinstance(row, dict)
                and row.get("symbol") in names
                and row["symbol"] not in by_symbol
                and row.get("session") == session
                and row.get("point_in_time_close_certified") is False
                and row.get("production_writes") is False,
                "NOCP_UPSTREAM_SYMBOL_SESSION_OR_CERTIFICATION_CONFLICT")
        by_symbol[row["symbol"]] = row
    require(set(by_symbol) == set(names), "NOCP_UPSTREAM_MISSING_ASSET")
    for name, digest in file_hashes.items():
        require(digest_ok(digest), "NOCP_SOURCE_HASH_INVALID")
    nasdaq_symbols = [
        name for name in names
        if by_symbol[name]["current_listed_venue"] == "NASDAQ"
    ]
    # The 2026-11-20 frozen baseline is known: 16 Nasdaq-listed route hints.
    # Future sessions may have listing transfers; never force future mapping.
    if session == "2026-11-20":
        require(len(nasdaq_symbols) == 16,
                "NOCP_FROZEN_BASELINE_ROUTE_COUNT_CHANGED")
    for sym in nasdaq_symbols:
        r = by_symbol[sym]
        require(r.get("publisher") == "Nasdaq"
                and r.get("access_status") ==
                "AUTHENTICATED_SESSION_NUMERIC_RECORD_NOT_CONNECTED_HOLD"
                and r.get("official_close_record_attached") is False
                and r.get("independently_licensed_final_close_attached") is False,
                "NOCP_PRIMARY_PUBLISHER_ROUTE_INVALID")
    require(isinstance(probes, dict) and
            set(probes).issubset(set(nasdaq_symbols)),
            "NOCP_UNKNOWN_PROBE_SYMBOL")
    if probe_attempted:
        require(set(probes) == set(nasdaq_symbols),
                "NOCP_PROBE_ALL_CURRENT_NASDAQ_REQUIRED")
    else:
        require(not probes, "NOCP_OFFLINE_PROBE_MUST_BE_EMPTY")
    rows = []
    for sym in nasdaq_symbols:
        p = probes.get(sym)
        require(p is None or
                (isinstance(p, dict)
                 and isinstance(p.get("probe_status"), str)
                 and p["probe_status"].endswith("_HOLD")
                 and (p.get("http_status") is None or
                      (type(p.get("http_status")) is int and
                       100 <= p["http_status"] <= 599))
                 and (p.get("response_sha256") is None or digest_ok(p["response_sha256"]))),
                "NOCP_PROBE_RESPONSE_SCHEMA_INVALID")
        rows.append({
            "symbol": sym, "session": session,
            "page_url": page_url(sym),
            "probe_attempted": bool(probe_attempted),
            "http_status": p.get("http_status") if p else None,
            "probe_status": p["probe_status"] if p else "NASDAQ_PAGE_NOT_FETCHED_OFFLINE_HOLD",
            "response_sha256": p.get("response_sha256") if p else None,
            "response_bytes": p.get("response_bytes") if p else None,
            "html_unavailable_placeholder": (p.get("html_unavailable_placeholder")
                                             if p else None),
            "nocp_price": None,
            "official_certified": False,
            "historical_listing_certified": False,
            "primary_market_center_M_promoted": False,
        })
    require(len(rows) == len(nasdaq_symbols)
            and all(x["nocp_price"] is None and
                    x["official_certified"] is False for x in rows),
            "NOCP_ANY_UNSUPPORTED_PRICE_ADMISSION")
    return {
        "version": VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "live_execution": False,
        "status": "NASDAQ_PUBLIC_NOCP_ACCESS_NOT_PRICE_CERTIFICATION_HOLD",
        "nasdaq_current_master_route_count": len(nasdaq_symbols),
        "public_pages_attempted": len(probes),
        "public_html_200_count": sum(x["http_status"] == 200 for x in rows),
        "public_unavailable_placeholders": sum(
            x["html_unavailable_placeholder"] is True for x in rows
        ),
        "official_nocp_numeric_records_admitted": 0,
        "independent_regular_close_certified": 0,
        "factor_certified": 0,
        "subscription_product": {
            "publisher": "Nasdaq",
            "product": "Nasdaq Fundamental Data",
            "documentation": FUNDAMENTAL_URL,
            "content": "T+1 Nasdaq Official Closing Price distinct from daily last sale",
            "access": "secured FTP or website; current business month; subscription approval",
            "authenticated_numeric_file_connected": False,
        },
        "other_entitled_product": {
            "product": "Nasdaq Basic (NBPL)",
            "documentation": NBPL_URL,
            "access": "subscriber entitlements unverified; NOCP values not ingested",
        },
        "probed_at_utc": fetched_at,
        "input_sha256": dict(file_hashes),
        "limitations": [
            "HTML may have dynamic data; absence in static HTML is not proof that the publisher has no NOCP.",
            "Nasdaq historical OHLCV or closing quote endpoints are not proof of NOCP.",
            "NOCP is Nasdaq market center official close, not the consolidated SIP last sale.",
            "Secure Fundamental Data or properly entitled primary source is required for numeric verification.",
            "Current Alpaca listing master does not certify historical as-of listing identity.",
        ],
        "rows": rows,
    }


def run(config, access_path, output, *, probe_public=False, fetcher=public_http_probe):
    sources = {"config": config, "access": access_path}
    raw = {k: Path(v).read_bytes() for k, v in sources.items()}
    files = {k: json.loads(v) for k, v in raw.items()}
    hashes = {k: sha256(v).hexdigest() for k, v in raw.items()}
    names = [r["symbol"] for r in files["access"].get("rows", [])
             if r.get("current_listed_venue") == "NASDAQ"]
    probes = {}
    if probe_public:
        # A maximum of four small public-page reads at once; PR/offline
        # contracts NEVER access external endpoints.
        with ThreadPoolExecutor(max_workers=4) as pool:
            for symbol, evidence in zip(names, pool.map(
                lambda s: fetcher(page_url(s)), names
            )):
                probes[symbol] = evidence
    now = datetime.now(timezone.utc).isoformat() if probe_public else None
    report = build(files["config"], files["access"],
                   probes=probes, probe_attempted=probe_public,
                   file_hashes=hashes, fetched_at=now)
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    csv_path = target / "public_portal_probe.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({k: row.get(k) for k in CSV_FIELDS})
    report["csv_sha256"] = sha256(csv_path.read_bytes()).hexdigest()
    (target / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("DAILY20_NASDAQ_NOCP_ACCESS_HOLD", report["session"],
          "routes", report["nasdaq_current_master_route_count"],
          "public_pages", report["public_pages_attempted"],
          "HTML200", report["public_html_200_count"],
          "NOCP_numeric", report["official_nocp_numeric_records_admitted"],
          "certified", report["independent_regular_close_certified"])
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--access", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--probe-public", action="store_true")
    a = p.parse_args()
    run(a.config, a.access, a.out_dir, probe_public=a.probe_public)


if __name__ == "__main__":
    main()
