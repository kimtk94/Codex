#!/usr/bin/env python3
"""Capture Nasdaq Trader symbol-directory listing evidence without retrojection.

Public official lists are current, mutable files. Record their own creation
timestamps, the exact response SHA256, and the fetch timestamp; NEVER backdate
the snapshot to the last completed trading session. Preserve a hash-chained
compact journal between Drive research ZIP revisions, but note that older raw
directory bytes are not retained by this journal. Research only: no LIVE
updates, model price substitutions, 16:00 price certification, or 2026-11-20
historical listing certification from a subsequently fetched directory.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO, BytesIO
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from daily20 import load_spec, write_json
from official_directory_history import preserve as preserve_full_source_history

VERSION = "daily20-official-directory-snapshot-v1"
URLS = {
    "nasdaqlisted": "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt",
    "otherlisted": "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt",
}
COLUMNS = {
    "nasdaqlisted": {"Symbol", "Security Name", "Test Issue", "ETF"},
    "otherlisted": {"ACT Symbol", "Security Name", "Exchange", "Test Issue", "ETF"},
}
JOURNAL_MEMBER = "research/official_directory/snapshot_journal.jsonl"
NY = ZoneInfo("America/New_York")
MAX_BYTES = 4_000_000
MAX_AGE_DAYS = 7
FOOTER = re.compile(r"^File Creation Time:\s*(\d{10}:\d{2})\s*$")


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def fetch_url(url):
    req = Request(url, headers={
        "User-Agent": "Kalman-Daily20-Research-Listing-Evidence/1.0",
        "Accept": "text/plain",
    })
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise ValueError("DIRECTORY_RESPONSE_NOT_OK")
        data = response.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("DIRECTORY_RESPONSE_EMPTY_OR_OVERSIZE")
    return data


def parse_directory(blob, name, *, min_rows=1000):
    if name not in URLS:
        raise ValueError("UNKNOWN_DIRECTORY")
    if not isinstance(blob, bytes) or not blob or len(blob) > MAX_BYTES:
        raise ValueError("DIRECTORY_BAD_BODY_SIZE")
    lines = blob.decode("utf-8-sig", errors="strict").splitlines()
    if len(lines) < 3:
        raise ValueError("DIRECTORY_TOO_SHORT")
    footer = lines[-1].split("|", 1)[0].strip()
    match = FOOTER.fullmatch(footer)
    if not match:
        raise ValueError("DIRECTORY_MISSING_CREATION_FOOTER")
    created = datetime.strptime(match.group(1), "%m%d%Y%H:%M").replace(tzinfo=NY)
    data = csv.DictReader(StringIO("\n".join(lines[:-1])), delimiter="|")
    if not data.fieldnames or not COLUMNS[name].issubset(data.fieldnames):
        raise ValueError("DIRECTORY_HEADER_SCHEMA_CHANGED")
    rows = {}
    count = 0
    for row in data:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("DIRECTORY_ROW_WIDTH_INVALID")
        symbol = (row["Symbol"] if name == "nasdaqlisted" else row["ACT Symbol"]).strip()
        if not symbol or symbol in rows:
            raise ValueError("DIRECTORY_SYMBOL_EMPTY_OR_DUPLICATE")
        test = row["Test Issue"].strip()
        etf = row["ETF"].strip()
        if test not in ("N", "Y") or etf not in ("N", "Y"):
            raise ValueError("DIRECTORY_TEST_ETF_FLAG_INVALID")
        exchange = "Q" if name == "nasdaqlisted" else row["Exchange"].strip()
        if not exchange:
            raise ValueError("DIRECTORY_MISSING_EXCHANGE")
        rows[symbol] = {
            "symbol": symbol, "exchange": exchange,
            "source": name, "test_issue": test == "Y", "etf": etf == "Y",
            "security_name": row["Security Name"].strip()[:220],
        }
        count += 1
    if count < min_rows:
        raise ValueError("DIRECTORY_ROWS_BELOW_MINIMUM")
    return {
        "source": name, "url": URLS[name], "sha256": sha256(blob).hexdigest(),
        "file_creation_et": created.isoformat(), "file_creation_date": created.date().isoformat(),
        "rows": count,
    }, rows


def _now_utc(stamp):
    obj = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if obj.tzinfo is None:
        raise ValueError("DIRECTORY_FETCH_TIME_NAIVE")
    return obj.astimezone(timezone.utc)


def verify_chain(lines):
    prev = "0" * 64
    for i, event in enumerate(lines):
        if not isinstance(event, dict):
            raise ValueError("DIRECTORY_JOURNAL_EVENT_INVALID")
        payload = {k: v for k, v in event.items() if k != "hash"}
        expected = sha256(canonical_bytes(payload)).hexdigest()
        if (event.get("seq") != i + 1 or event.get("prev_hash") != prev
                or event.get("hash") != expected):
            raise ValueError("DIRECTORY_JOURNAL_CHAIN_INVALID")
        prev = expected
    return prev


def previous_chain(prior_zip):
    if prior_zip is None:
        return [], "NO_PRIOR_ARCHIVE_PR"
    path = Path(prior_zip)
    if not path.is_file():
        return [], "PRIOR_DRIVE_ARCHIVE_MISSING_HOLD"
    with ZipFile(path) as archive:
        members = archive.namelist()
        if JOURNAL_MEMBER not in members:
            return [], "FIRST_OFFICIAL_DIRECTORY_CAPTURE"
        raw = archive.read(JOURNAL_MEMBER)
    lines = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    verify_chain(lines)
    return lines, "CONTINUED_FROM_PRIOR_DRIVE_RESULTS"


def one_snapshot(spec, responses, *, fetched_at, current_venue=None):
    names = [s for s in spec["core"] + spec["context"] if s != "^VIX"]
    if len(names) != 25 or len(set(names)) != 25:
        raise ValueError("DIRECTORY_EXPECTED_25_NAMES")
    fetch_utc = _now_utc(fetched_at)
    summaries, records = {}, {}
    stale = False
    for source in URLS:
        meta, rows = parse_directory(responses[source], source)
        creation = datetime.fromisoformat(meta["file_creation_et"]).astimezone(timezone.utc)
        delta = fetch_utc - creation
        if delta < -timedelta(minutes=15) or delta > timedelta(days=MAX_AGE_DAYS):
            stale = True
        summaries[source] = meta
        records[source] = rows
    venue_lookup = {}
    if current_venue is not None:
        if current_venue.get("tested_assets") != 25 or current_venue.get("finality_verified") != 0:
            raise ValueError("DIRECTORY_ALPACA_VENUE_REFERENCE_INVALID")
        for v in current_venue.get("rows", []):
            sym = v.get("symbol")
            if not isinstance(sym, str) or sym in venue_lookup:
                raise ValueError("DIRECTORY_ALPACA_DUPLICATE_IDENTITY")
            venue_lookup[sym] = v
        if set(venue_lookup) != set(names):
            raise ValueError("DIRECTORY_ALPACA_25_UNIVERSE_MISMATCH")
    out = []
    for symbol in names:
        matches = [r[symbol] for r in records.values() if symbol in r]
        if len(matches) == 0:
            status, listing = "OFFICIAL_DIRECTORY_SYMBOL_MISSING_HOLD", None
        elif len(matches) > 1:
            status, listing = "OFFICIAL_DIRECTORY_MULTIPLE_LISTINGS_HOLD", None
        elif matches[0]["test_issue"]:
            status, listing = "OFFICIAL_DIRECTORY_TEST_ISSUE_HOLD", matches[0]
        elif matches[0]["exchange"] not in ("Q", "N", "P", "A", "Z", "V"):
            status, listing = "OFFICIAL_DIRECTORY_UNKNOWN_EXCHANGE_HOLD", matches[0]
        elif stale:
            status, listing = "OFFICIAL_DIRECTORY_STALE_SNAPSHOT_HOLD", matches[0]
        else:
            status, listing = "OFFICIAL_DIRECTORY_LISTING_OBSERVED_RESEARCH_ONLY", matches[0]
        candidate = {
            "symbol": symbol, "status": status, "venue": listing["exchange"] if listing else None,
            "source": listing["source"] if listing else None,
            "security_name": listing["security_name"] if listing else None,
            "etf": listing["etf"] if listing else None,
            "observed_snapshot_only": True,
            "historical_session_listing_certified": False,
            "regular_close_price_certified": False,
        }
        if symbol in venue_lookup:
            v = venue_lookup[symbol]
            candidate["alpaca_current_master_primary_venue"] = v.get("selected_primary_venue_code")
            code = candidate["venue"]
            alpaca = candidate["alpaca_current_master_primary_venue"]
            if code is None or alpaca is None:
                candidate["comparison"] = "VENUE_MISSING_HOLD"
            elif code == alpaca:
                candidate["comparison"] = "CURRENT_SNAPSHOT_NUMERIC_VENUE_CODE_MATCH_UNCERTIFIED"
            else:
                candidate["comparison"] = "OFFICIAL_DIRECTORY_VS_ALPACA_VENUE_CONFLICT_HOLD"
                candidate["status"] = "OFFICIAL_DIRECTORY_VS_ALPACA_VENUE_CONFLICT_HOLD"
        out.append(candidate)
    result = {
        "version": VERSION, "fetched_at_utc": fetch_utc.isoformat(),
        "research_only": True, "production_writes": False, "strategy_promoted": False,
        "source_snapshot_is_historical_asof_evidence": False,
        "current_session_close_certified": False, "finality_verified": 0,
        "required": 25, "sources": summaries, "rows": out,
        "snapshot_listed_count": sum(x["venue"] is not None for x in out),
        "research_listing_observed": sum(
            x["status"] == "OFFICIAL_DIRECTORY_LISTING_OBSERVED_RESEARCH_ONLY" for x in out),
        "venue_disagreements": sum(
            x.get("comparison") == "OFFICIAL_DIRECTORY_VS_ALPACA_VENUE_CONFLICT_HOLD" for x in out),
        "source_stale": stale, "status": "OFFICIAL_DIRECTORY_SNAPSHOT_RESEARCH_HOLD",
    }
    return result


def save_journal(prior, result, *, prior_status):
    current = {
        "created_at_utc": result["fetched_at_utc"],
        "source_file_dates": {key: val["file_creation_date"] for key, val in result["sources"].items()},
        "source_sha256": {key: val["sha256"] for key, val in result["sources"].items()},
        "symbols": {x["symbol"]: x["venue"] for x in result["rows"]},
    }
    journal = list(prior)
    decision = "NEW_OFFICIAL_SNAPSHOT_APPEND"
    if journal and journal[-1]["source_sha256"] == current["source_sha256"]:
        decision = "IDENTICAL_SOURCE_SNAPSHOT_ALREADY_SEALED"
    else:
        observed_dates = current["source_file_dates"]
        if journal and journal[-1]["source_file_dates"] == observed_dates:
            decision = "SAME_FILE_CREATION_DATES_CHANGED_BYTES_HOLD"
        prev = verify_chain(journal)
        payload = {
            "seq": len(journal) + 1, "prev_hash": prev,
            "version": VERSION, **current,
        }
        journal.append({**payload, "hash": sha256(canonical_bytes(payload)).hexdigest()})
    verify_chain(journal)
    return journal, {
        "status": decision, "previous_archive_status": prior_status,
        "journal_events": len(journal),
        "journal_tip_sha256": journal[-1]["hash"] if journal else None,
        "earlier_full_source_bytes_preserved": False,
        "current_snapshot_not_retrojected": True,
    }


def run(spec, out_dir, *, fetcher=fetch_url, stamp=None,
        prior_zip=None, current_venue=None, preview=False):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).isoformat()
    prior, prior_status = previous_chain(prior_zip)
    result = {
        "version": VERSION, "fetched_at_utc": stamp,
        "research_only": True, "production_writes": False, "strategy_promoted": False,
        "finality_verified": 0, "required": 25, "status": "OFFICIAL_DIRECTORY_FETCH_HOLD",
        "source_snapshot_is_historical_asof_evidence": False,
    }
    responses = None
    try:
        responses = {key: fetcher(url) for key, url in URLS.items()}
        result = one_snapshot(spec, responses, fetched_at=stamp, current_venue=current_venue)
        raw_dir = out / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        for key, blob in responses.items():
            (raw_dir / (key + ".txt")).write_bytes(blob)
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError, UnicodeError,
            json.JSONDecodeError) as exc:
        result["error_class"] = (
            "HTTP_" + str(exc.code) if isinstance(exc, HTTPError) else type(exc).__name__)
        result["status"] = "OFFICIAL_DIRECTORY_SOURCE_UNAVAILABLE_HOLD"
    if (result.get("sources") and not preview
            and prior_status != "PRIOR_DRIVE_ARCHIVE_MISSING_HOLD"):
        journal, evidence = save_journal(prior, result, prior_status=prior_status)
    else:
        journal = prior
        evidence = {
            "status": ("PR_PREVIEW_NO_SEAL" if preview
                       else "PRIOR_DRIVE_ARCHIVE_MISSING_HOLD"
                       if prior_status == "PRIOR_DRIVE_ARCHIVE_MISSING_HOLD"
                       else "NO_SOURCE_SNAPSHOT_APPEND_HOLD"),
            "previous_archive_status": prior_status, "journal_events": len(journal),
            "journal_tip_sha256": journal[-1]["hash"] if journal else None,
            "earlier_full_source_bytes_preserved": False,
            "current_snapshot_not_retrojected": True,
        }
    # Existing journal is verified before any source bytes are replayed.
    # A transient fetch failure still copies the old sealed raw bodies forward.
    if preview:
        result["source_history"] = {
            "status": "PR_PREVIEW_UNSEALED",
            "all_journal_digests_attested_by_raw_bytes": False,
            "raw_body_history_preserved_in_pinned_drive_zip": False,
            "regular_close_or_point_in_time_listing_certified": False,
        }
    else:
        result["source_history"] = preserve_full_source_history(
            prior_zip, journal,
            responses if (result.get("sources") and
                          prior_status != "PRIOR_DRIVE_ARCHIVE_MISSING_HOLD") else None,
            out)
        evidence["earlier_full_source_bytes_preserved"] = result[
            "source_history"]["all_journal_digests_attested_by_raw_bytes"]
        if (result["source_history"]["status"] != "FULL_SOURCE_BYTES_VERIFIED"
                or prior_status == "PRIOR_DRIVE_ARCHIVE_MISSING_HOLD"):
            result["status"] = "OFFICIAL_DIRECTORY_SOURCE_HISTORY_INCOMPLETE_HOLD"
    result["journal"] = evidence
    if not preview:
        (out / "snapshot_journal.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
                    for row in journal), encoding="utf-8")
    write_json(out / "report.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--prior-zip")
    p.add_argument("--current-venue")
    p.add_argument("--preview", action="store_true")
    a = p.parse_args()
    venue = json.loads(Path(a.current_venue).read_text()) if a.current_venue else None
    result = run(load_spec(a.config), a.out_dir, prior_zip=a.prior_zip,
                 current_venue=venue, preview=a.preview)
    print("DAILY20_OFFICIAL_DIRECTORY", result["status"],
          result.get("research_listing_observed", 0), "/25 venue snapshot observed;",
          "historical certified 0; finality 0/26; journal",
          result["journal"]["status"], "full source",
          result["source_history"]["status"],
          result["source_history"].get("raw_source_blob_count", 0))


if __name__ == "__main__":
    main()
