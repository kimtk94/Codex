#!/usr/bin/env python3
"""Read-only Alpaca market-data corporate-action evidence, never price certification.

Only the protected GitHub environment may send authenticated requests. The
endpoint filters by PROCESS DATE, not ex-date; reported events can lag. Actions
are vendor observations, not independently certified Yahoo adjustment factors,
exchange 16:00 close evidence, or historical listing provenance.
"""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from collect_independent_close import http_bytes, utc_time
from daily20 import load_spec, write_json

VERSION = "daily20-alpaca-ca-reference-v1"
ENDPOINT = "https://data.alpaca.markets/v1/corporate-actions"
MAX_PAGES = 12
MAX_RESPONSE_BYTES = 5_000_000
START = "2017-01-01"
FIELDS = (
    "id", "symbol", "process_date", "ex_date", "effective_date",
    "record_date", "payable_date", "currency", "rate", "old_rate",
    "new_rate", "sub_type", "cusip", "isin", "old_symbol", "new_symbol",
    # Event-type specific identities; merger/name-change schemas do NOT have
    # a universal "symbol" field. Never infer a single price-series identity.
    "acquiree_symbol", "acquirer_symbol", "source_symbol",
    "old_cusip", "new_cusip", "acquiree_cusip", "acquirer_cusip",
    "source_cusip",
)
IDENTITY_ROLES = ("old_symbol", "new_symbol", "acquiree_symbol",
                  "acquirer_symbol", "source_symbol")
ROLE_ONLY_GROUPS = ("cash_mergers", "stock_mergers",
                    "stock_and_cash_mergers", "name_changes",
                    "unit_splits", "spin_offs", "rights_distributions")

# Never silently drop other classes: they can affect price comparability.
KNOWN_GROUPS = {
    "cash_dividends", "capital_gains_distributions", "forward_splits",
    "reverse_splits", "unit_splits", "stock_dividends", "spin_offs",
    "cash_mergers", "stock_mergers", "stock_and_cash_mergers",
    "redemptions", "name_changes", "worthless_removals",
    "rights_distributions", "partial_calls", "reorganizations",
}


def _headers():
    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        return None
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json"}


def _error(exc):
    if isinstance(exc, HTTPError):
        return "HTTP_" + str(exc.code)
    if isinstance(exc, (URLError, TimeoutError)):
        return "NETWORK_UNAVAILABLE"
    return type(exc).__name__


def _iso(value):
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def parse_page(blob, queried, page_number):
    """Require typed top-level body and preserve every supported event class."""
    data = json.loads(blob)
    if not isinstance(data, dict) or not isinstance(data.get("corporate_actions"), dict):
        raise ValueError("CA_RESPONSE_SCHEMA_INVALID")
    if "next_page_token" not in data:
        raise ValueError("CA_PAGINATION_TOKEN_MISSING")
    token = data["next_page_token"]
    if token is not None and (not isinstance(token, str) or not token):
        raise ValueError("CA_PAGINATION_TOKEN_INVALID")
    digest = sha256(blob).hexdigest()
    out, malformed, unexpected_groups, unmapped_identity = [], 0, [], []
    for group, items in data["corporate_actions"].items():
        if group not in KNOWN_GROUPS:
            unexpected_groups.append(group)
        if not isinstance(items, list):
            raise ValueError("CA_ACTION_GROUP_NOT_ARRAY")
        for item in items:
            if not isinstance(item, dict):
                malformed += 1
                continue
            symbol = item.get("symbol")
            if not isinstance(symbol, str) or symbol not in queried:
                # Alpaca mergers and name changes commonly use `acquiree_symbol`,
                # `acquirer_symbol`, `old_symbol`, `new_symbol` instead of
                # generic `symbol`. Preserve both roles with no guessed issuer
                # mapping and never insert these into price-factor comparisons.
                roles = {
                    key: item[key] for key in IDENTITY_ROLES
                    if isinstance(item.get(key), str) and 0 < len(item[key]) <= 24
                }
                matches = {key: val for key, val in roles.items() if val in queried}
                expected_role_schema = (group in ROLE_ONLY_GROUPS
                                        and not isinstance(symbol, str)
                                        and bool(roles))
                if not expected_role_schema:
                    malformed += 1
                unmapped_identity.append({
                    "group": group,
                    "returned_symbol": symbol if isinstance(symbol, str) and len(symbol) <= 24 else None,
                    "event_id": item.get("id") if isinstance(item.get("id"), str) else None,
                    "process_date": item.get("process_date") if isinstance(item.get("process_date"), str) else None,
                    "ex_date": item.get("ex_date") if isinstance(item.get("ex_date"), str) else None,
                    "identity_roles": roles,
                    "queried_symbol_role_candidates": matches,
                    "identity_schema": (
                        "EXPECTED_EVENT_TYPE_ROLE_FIELDS_UNCERTIFIED"
                        if expected_role_schema else
                        "UNEXPECTED_OR_UNLINKABLE_IDENTITY_HOLD"
                    ),
                    "issuer_lineage_certified": False,
                })
                continue
            # Incomplete events are deliberately retained, but excluded from
            # matched ex-date evaluation until the missing fields are known.
            typed = {"type": group, "source_page_sha256": digest,
                     "page_number": page_number}
            bad_fields = []
            for key in FIELDS:
                value = item.get(key)
                if value is None or isinstance(value, (str, int, float, bool)):
                    typed[key] = value
                else:
                    typed[key] = None
                    bad_fields.append(key)
                    malformed += 1
            if bad_fields:
                typed["unexpected_non_scalar_fields"] = bad_fields
            if not _iso(typed["process_date"]):
                malformed += 1
                typed["invalid_process_date"] = True
            if typed["ex_date"] is not None and not _iso(typed["ex_date"]):
                malformed += 1
                typed["invalid_ex_date"] = True
            out.append(typed)
    return out, token, digest, malformed, sorted(unexpected_groups), unmapped_identity


def collect(symbols, session, *, fetcher=http_bytes, offline=False, stamp=None):
    if not _iso(session):
        raise ValueError("INVALID_SESSION")
    if date.fromisoformat(session) < date.fromisoformat(START):
        raise ValueError("SESSION_PREDATES_COLLECTOR_RANGE")
    if len(symbols) != 25 or len(set(symbols)) != 25 or "^VIX" in symbols:
        raise ValueError("EXPECTED_25_UNIQUE_EQUITY_ETF_SYMBOLS")
    stamp = stamp or utc_time()
    report = {
        "version": VERSION, "session": session,
        "source": "Alpaca Market Data Corporate Actions v1",
        "endpoint": ENDPOINT, "query_start_process_date": START,
        "query_end_process_date": session,
        "date_filter_semantics": "PROCESS_DATE_NOT_EX_DATE",
        "data_quality": "all", "region": "us",
        "queried_symbols": list(symbols),
        "fetched_at_utc": stamp,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "factor_independently_certified": 0,
        "finality_verified": 0, "page_sha256": [], "page_count": 0,
        "events": [], "status": "SOURCE_UNAVAILABLE_HOLD",
        "historical_identity_certified": False,
    }
    if offline:
        report["status"] = "CREDENTIALS_ISOLATED_PR_HOLD"
        return report
    headers = _headers()
    if headers is None:
        report["status"] = "CREDENTIALS_NOT_CONFIGURED_HOLD"
        return report
    query = {
        "symbols": ",".join(symbols), "start": START, "end": session,
        "region": "us", "data_quality": "all", "limit": 1000, "sort": "asc",
    }
    token = None
    visited = set()
    malformed = 0
    unsupported = set()
    unmapped_identity = []
    seen_ids = set()
    try:
        for i in range(MAX_PAGES):
            if token:
                query["page_token"] = token
            url = ENDPOINT + "?" + urlencode(query)
            # Never write the URL or credential-bearing headers to logs/evidence.
            blob = fetcher(url, headers, limit=MAX_RESPONSE_BYTES)
            page, next_token, digest, invalid, unknown, unmapped = parse_page(
                blob, set(symbols), i + 1)
            report["page_sha256"].append(digest)
            report["page_count"] += 1
            malformed += invalid
            unsupported.update(unknown)
            unmapped_identity.extend(unmapped)
            for item in page:
                event_id = item.get("id")
                if not isinstance(event_id, str) or not event_id:
                    malformed += 1
                elif (item["type"], event_id) in seen_ids:
                    malformed += 1
                else:
                    seen_ids.add((item["type"], event_id))
                report["events"].append(item)
            if next_token is None:
                break
            if next_token in visited:
                report["status"] = "PAGINATION_LOOP_HOLD"
                return report
            visited.add(next_token)
            token = next_token
        else:
            report["status"] = "PAGE_LIMIT_REACHED_HOLD"
            return report
    except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError,
            TypeError, json.JSONDecodeError) as exc:
        report["status"] = "SOURCE_FETCH_OR_SCHEMA_HOLD"
        report["error_class"] = _error(exc)
        return report
    report["malformed_or_ambiguous_count"] = malformed
    report["unmapped_historical_identity_count"] = len(unmapped_identity)
    report["role_based_identity_event_count"] = sum(
        x["identity_schema"] == "EXPECTED_EVENT_TYPE_ROLE_FIELDS_UNCERTIFIED"
        for x in unmapped_identity)
    report["queried_symbol_role_link_candidates"] = sum(
        bool(x["queried_symbol_role_candidates"]) for x in unmapped_identity)
    report["issuer_lineage_certified"] = False
    report["unmapped_historical_identity_examples"] = unmapped_identity[:32]
    report["non_scalar_field_count"] = sum(
        bool(x.get("unexpected_non_scalar_fields")) for x in report["events"])
    report["unknown_action_groups"] = sorted(unsupported)
    report["event_count"] = len(report["events"])
    report["per_symbol_events"] = {
        symbol: sum(e.get("symbol") == symbol for e in report["events"])
        for symbol in symbols
    }
    report["status"] = (
        "ALPACA_ACTIONS_RETRIEVED_UNCERTIFIED"
        if not malformed and not unsupported and not unmapped_identity
        else "ALPACA_ACTIONS_INCOMPLETE_OR_UNKNOWN_HOLD")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--session", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    spec = load_spec(args.config)
    names = [x for x in spec["core"] + spec["context"] if x != "^VIX"]
    report = collect(names, args.session, offline=args.offline)
    write_json(Path(args.out), report)
    # Status summaries have no secret, page token or full request URL.
    print("DAILY20_ALPACA_CA", report["status"], "pages",
          report["page_count"], "events", len(report["events"]),
          "FACTOR_CERTIFIED", report["factor_independently_certified"])


if __name__ == "__main__":
    main()
