#!/usr/bin/env python3
"""Capture ProShares' own year-scoped QLD distribution JSON, read-only.

The 2023-09-20 event may be present or absent in today's issuer API. Absence
is evidence of API coverage only, NOT proof that a historical payment did not
occur. A cash row, if present, is NOT a certified price adjustment factor.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://www.proshares.com/api/distributionsummary?fund=QLD&year=2023"
VERSION = "daily20-qld2023-issuer-distribution-api-v3"
TARGET = "2023-09-20"
LIMIT = 1_000_000

def get_json_bytes(url=URL):
    if url != URL:
        raise ValueError("QLD_SOURCE_URL_MUST_BE_PINNED")
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "KalmanDaily20ResearchEvidence/1.0",
    })
    with urlopen(req, timeout=27) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "www.proshares.com":
            raise ValueError("QLD_UNTRUSTED_SOURCE_REDIRECT")
        if response.status != 200:
            raise ValueError("QLD_SOURCE_NON_200")
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT or not raw:
        raise ValueError("QLD_SOURCE_EMPTY_OR_OVERSIZE")
    return raw

def parse_day(value):
    if not isinstance(value, str):
        return None
    s = value.strip()
    # ProShares' original year-scoped API uses naive ISO datetimes such as
    # 2023-12-20T00:00:00. These are calendar dates, not UTC instants:
    # preserve the written day and do not apply timezone conversion.
    formats = ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S",
               "%d-%b-%Y", "%b %d %Y", "%b %d, %Y")
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None

def amount(v):
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not d.is_finite() or d < 0:
        return None
    return str(d)

def inspect(raw: bytes):
    obj = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(obj, list):
        raise ValueError("QLD_API_NOT_JSON_ARRAY")
    if len(obj) > 200:
        raise ValueError("QLD_API_UNEXPECTED_ROW_COUNT")
    rows = []
    for item in obj:
        if not isinstance(item, dict):
            raise ValueError("QLD_API_ROW_NOT_OBJECT")
        sym = item.get("Symbol")
        if sym not in (None, "", "QLD"):
            raise ValueError("QLD_API_SECURITY_ID_MISMATCH")
        day = parse_day(item.get("ExDate"))
        if day is None:
            raise ValueError("QLD_API_MISSING_OR_INVALID_EXDATE")
        if not day.startswith("2023-"):
            raise ValueError("QLD_API_YEAR_MISMATCH")
        dividend = amount(item.get("Dividend"))
        raw_cash = amount(item.get("CashDividendPerShare"))
        if item.get("Dividend") not in (None,"") and dividend is None:
            raise ValueError("QLD_API_INVALID_DIVIDEND")
        if item.get("CashDividendPerShare") not in (None,"") and raw_cash is None:
            raise ValueError("QLD_API_INVALID_CASH")
        if dividend is not None and raw_cash is not None and Decimal(dividend) != Decimal(raw_cash):
            raise ValueError("QLD_API_CASH_FIELDS_DISAGREE")
        rows.append({
            "ex_date": day, "record_date": parse_day(item.get("RecordDate")),
            "payable_date": parse_day(item.get("PayableDate")),
            "cash_dividend_as_published_usd": dividend if dividend is not None else raw_cash,
            "cash_share_unit_basis_certified": False,
            "source_symbol": sym, "raw_keys": sorted(item.keys())
        })
    hits = [r for r in rows if r["ex_date"] == TARGET]
    if len(hits) > 1:
        raise ValueError("QLD_API_DUPLICATE_TARGET_ROWS")
    return rows, hits[0] if hits else None

def classify_response(raw: bytes) -> str:
    """Safe classification only; never log untrusted remote HTML or response text."""
    prefix = raw.lstrip()[:1]
    if prefix == b"[":
        return "JSON_ARRAY_CANDIDATE"
    if prefix == b"{":
        return "JSON_OBJECT_CANDIDATE"
    if prefix == b"<":
        return "HTML_OR_XML"
    return "OTHER_TEXT_OR_BINARY"


def safe_failure_code(exc: Exception) -> str:
    """Stable, bounded codes; avoid printing raw exception messages or URLs."""
    if isinstance(exc, HTTPError):
        return "HTTP_STATUS_" + str(exc.code) if 100 <= exc.code <= 599 else "HTTP_STATUS_UNKNOWN"
    if isinstance(exc, URLError):
        return "URL_TRANSPORT_ERROR"
    if isinstance(exc, json.JSONDecodeError):
        return "QLD_API_INVALID_JSON"
    if isinstance(exc, UnicodeDecodeError):
        return "QLD_API_INVALID_UTF8"
    if isinstance(exc, ValueError):
        code = str(exc)
        if code.startswith("QLD_") and code.replace("_", "").isalnum() and code.upper() == code and len(code) <= 80:
            return code
        return "UNCLASSIFIED_VALUE_ERROR"
    if isinstance(exc, TimeoutError):
        return "SOURCE_TIMEOUT"
    if isinstance(exc, OSError):
        return "SOURCE_OS_ERROR"
    return "UNCLASSIFIED_ERROR"


def run(*, offline=False, getter=get_json_bytes, out_dir=None):
    report = {
        "version": VERSION, "source_url": URL, "fund": "QLD", "year": 2023,
        "queried_ex_date": TARGET, "research_only": True,
        "production_writes": False, "strategy_promoted": False,
        "source_finality_verified": 0,
        "issuer_payment_finality_certified": False,
        "independent_adjustment_factor_certified": False,
        "independent_close_certified": False,
        "historical_nonpayment_proven": False,
        "historical_api_completeness_certified": False,
        "published_dividend_share_unit_basis": "UNDETERMINED_POSSIBLY_SPLIT_ADJUSTED",
        "status": "PR_OFFLINE_NO_SOURCE_HOLD" if offline else "ISSUER_API_FETCH_PENDING_HOLD",
        "fetched_at_utc": None, "source_sha256": None, "source_archive": None,
        "source_bytes": None, "source_response_kind": None,
        "source_fetched_but_schema_rejected": False,
        "api_2023_row_count": None, "api_ex_dates": None,
        "issuer_api_target_row": None,
        "fetch_error_type": None, "fetch_error_code": None,
        "failure_stage": None
    }
    if offline:
        return report
    stage = "SOURCE_FETCH"
    try:
        raw = getter(URL)
        stage = "SOURCE_BODY_VALIDATE"
        if not isinstance(raw, bytes) or not raw or len(raw) > LIMIT:
            raise ValueError("QLD_API_SOURCE_BYTES_INVALID")
        # Crucial forensic contract: preserve the *original response* even if
        # parsing or domain-specific schema validation later fails.
        report.update({
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_sha256": sha256(raw).hexdigest(),
            "source_bytes": len(raw),
            "source_response_kind": classify_response(raw),
        })
        if out_dir is not None:
            folder = Path(out_dir)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "qld_2023_proshares_api_raw_response.bin.gz"
            path.write_bytes(gzip.compress(raw, mtime=0))
            report["source_archive"] = path.name
        stage = "API_SCHEMA_VALIDATE"
        rows, hit = inspect(raw)
        report.update({
            "api_2023_row_count": len(rows),
            "api_ex_dates": sorted(r["ex_date"] for r in rows),
            "issuer_api_target_row": hit,
            "status": ("ISSUER_API_2023_TARGET_ROW_PRESENT_CASH_UNCERTIFIED"
                       if hit is not None else "ISSUER_API_2023_TARGET_ROW_ABSENT_HISTORY_HOLD"),
        })
    except (OSError, ValueError, TypeError, UnicodeDecodeError) as exc:
        report["status"] = "ISSUER_API_FETCH_OR_SCHEMA_FAILED_HOLD"
        report["fetch_error_type"] = type(exc).__name__
        report["fetch_error_code"] = safe_failure_code(exc)
        report["failure_stage"] = stage
        report["source_fetched_but_schema_rejected"] = stage == "API_SCHEMA_VALIDATE"
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",default="output/daily20/research/issuer_qld2023_api")
    p.add_argument("--offline",action="store_true")
    args=p.parse_args()
    report=run(offline=args.offline,out_dir=args.out_dir)
    dest=Path(args.out_dir)/"report.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("DAILY20_QLD2023_OFFICIAL_API",report["status"],
          "rows",report["api_2023_row_count"],"failure_code",report["fetch_error_code"],"CASH_FACTOR_HOLD")
if __name__=="__main__":
    main()
