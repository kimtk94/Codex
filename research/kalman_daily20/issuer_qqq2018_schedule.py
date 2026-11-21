#!/usr/bin/env python3
"""Issuer-origin 2018 QQQ *schedule rule* only; never an amount certification.

Read the original January 26 2018 trust amendment signed by the sponsor and trustee.
Archived raw HTML is hashed. The scheduled ex-date is a rule-derived candidate,
not issuer proof that cash was actually declared or paid on that date.
"""
from __future__ import annotations
import argparse
from datetime import date, timedelta
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re

from issuer_ca_primary_evidence import fetch_bytes, text_of_html

SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/1067839/000119312518023862/d423471dex99a3f.htm"
SOURCE_ID = "QQQ_SPONSOR_TRUST_AMENDMENT_6_2018"
VERSION = "daily20-qqq2018-issuer-schedule-v1"
EFFECTIVE = "January 26, 2018"
ANCHOR = ("The regular quarterly ex-dividend date for PowerShares QQQ Trust will "
          "be the first Business Day subsequent to the third Friday in each of "
          "March, June, September and December")
SCOPE = "OFFICIAL_2018_TRUST_SCHEDULE_ONLY_NOT_CASH_PAYMENT"

def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    days_until_friday = (4 - first.weekday()) % 7
    return first + timedelta(days=days_until_friday + 14)

def expected_exdate(year: int, month: int) -> str:
    if month not in (3, 6, 9, 12):
        raise ValueError("QQQ_NON_QUARTERLY_MONTH")
    friday = third_friday(year, month)
    # This clause is for the first business day after Friday. For June 2018,
    # that next Monday is a NYSE session and not a US market holiday.
    monday = friday + timedelta(days=3)
    if monday.weekday() != 0:
        raise AssertionError("QQQ_EXPECTED_MONDAY")
    if (year, month) != (2018, 6):
        raise ValueError("QQQ_RULE_NOT_EXTENDED_BEYOND_RESEARCH_CASE")
    return monday.isoformat()

def verify_document(raw: bytes) -> dict:
    body = text_of_html(raw)
    normalized = " ".join(body.split())
    sponsor = "Invesco PowerShares Capital Management LLC"
    trustee = "The Bank of New York Mellon"
    required = (EFFECTIVE, "Amendment No. 6", sponsor, trustee, ANCHOR)
    present = {part: part.lower() in normalized.lower() for part in required}
    return {
        "required_anchors_present": present,
        "source_anchor_verified": all(present.values()),
        "source_sha256": sha256(raw).hexdigest(),
        "source_size_bytes": len(raw),
    }

def build_report(*, offline: bool = False, getter=fetch_bytes, outdir: str | Path | None = None) -> dict:
    result = {
        "version": VERSION, "research_only": True, "production_writes": False,
        "strategy_promoted": False, "source_url": SOURCE_URL,
        "source_id": SOURCE_ID, "source_evidence_scope": SCOPE,
        "amendment_date": "2018-01-26", "third_friday_date": third_friday(2018,6).isoformat(),
        "rule_derived_ex_date": expected_exdate(2018, 6),
        "matched_qqq_exception_date": expected_exdate(2018, 6) == "2018-06-18",
        "issuer_cash_payment_certified": False, "issuer_paid_cash_amount_usd": None,
        "issuer_distribution_declared_for_case": False,
        "independent_adjustment_factor_certified": False,
        "independent_close_certified": False, "source_finality_verified": 0,
        "status": "OFFLINE_NO_DOCUMENT_HOLD" if offline else "FETCH_PENDING_HOLD",
        "source_archive": None, "source_sha256": None,
        "source_anchor_verified": False,
        "fetch_error_type": None,
    }
    if offline:
        return result
    try:
        raw = getter(SOURCE_URL)
        facts = verify_document(raw)
        result.update(facts)
        if not facts["source_anchor_verified"]:
            result["status"] = "FIRST_PARTY_RULE_SOURCE_ANCHORS_MISSING_HOLD"
        else:
            result["status"] = "FIRST_PARTY_2018_RULE_VERIFIED_CASH_HOLD"
        if outdir is not None:
            folder = Path(outdir)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "qqq_2018_amendment_6_original.html.gz"
            path.write_bytes(gzip.compress(raw, mtime=0))
            result["source_archive"] = path.name
    except (OSError, ValueError, TimeoutError) as exc:
        result["status"] = "ISSUER_RULE_SOURCE_FETCH_OR_PARSE_FAILED_HOLD"
        result["fetch_error_type"] = type(exc).__name__
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="output/daily20/research/issuer_qqq2018_rule")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    result = build_report(offline=args.offline, outdir=args.out_dir)
    out = Path(args.out_dir) / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DAILY20_QQQ2018_RULE", result["status"], "date", result["rule_derived_ex_date"], "CASH_HOLD")

if __name__ == "__main__":
    main()
