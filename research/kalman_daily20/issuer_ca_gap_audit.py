#!/usr/bin/env python3
"""Research-only follow-up for two unresolved Daily20 dividend events.

Archived primary-source bodies must match SHA-256, but checked source anchors
do not certify a 2018/2023 cash payment, adjustment, or 16:00 close.
"""
from __future__ import annotations
import argparse
import csv
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha256
import json
from pathlib import Path

VERSION = "daily20-issuer-ca-gap-audit-v1"
TARGETS = (
    ("QQQ", "2018-06-18", "QQQ_2018_SEC_2020_Q3_TABLE"),
    ("QLD", "2023-09-20", "QLD_2025_FORM_8937_SPLIT"),
)
UNARCHIVED_LEADS = {
    "QQQ": [
        {"role": "FIRST_PARTY_2018_FISCAL_ANNUAL_REPORT_AGGREGATE_NOT_EVENT",
         "url": "https://www.sec.gov/Archives/edgar/data/1067839/000119312518355790/d638310dn30b2.htm",
         "status": "RESEARCH_LEAD_NOT_FETCHED_NO_EX_DATE_AMOUNT"},
        {"role": "CONTEMPORANEOUS_THIRD_PARTY_2018_06_15_DECLARATION",
         "url": "https://www.dividendinvestor.com/dividend-news/20180615/invesco-qqq-trust-nasdaq-qqq-declared-a-dividend-of-%240.3764-per-share/",
         "reported_rounded_usd": "0.3764",
         "status": "RESEARCH_LEAD_NOT_FETCHED_NOT_ISSUER_ATTESTATION"},
        {"role": "THIRD_PARTY_EX_DATE_AMOUNT_REFERENCE",
         "url": "https://app.tiingo.com/qqq/dividends",
         "status": "RESEARCH_LEAD_NOT_FETCHED_NOT_ISSUER_ATTESTATION"},
    ],
    "QLD": [
        {"role": "THIRD_PARTY_PRE_SPLIT_CASH_CANDIDATE",
         "url": "https://etfiq.com/funds/qld/dividends/",
         "reported_raw_2023_cash_usd": "0.176282",
         "status": "RESEARCH_LEAD_NOT_FETCHED_NOT_ISSUER_ATTESTATION"},
        {"role": "THIRD_PARTY_SPLIT_ADJUSTED_CASH_CANDIDATE",
         "url": "https://stockanalysis.com/etf/qld/dividend/",
         "reported_adjusted_cash_usd": "0.08814",
         "status": "RESEARCH_LEAD_NOT_FETCHED_NOT_ISSUER_ATTESTATION"},
    ],
}

def number(v):
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v))
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None

def source_status(base, source, key):
    if not source or source.get("status") != "FETCHED_SOURCE_UNCERTIFIED":
        return "SOURCE_NOT_FETCHED_HOLD"
    if source.get("anchor_grade_by_claim", {}).get(key) != "BOTH_NEARBY_ANCHORS_OBSERVED":
        return "SOURCE_ANCHORS_MISSING_HOLD"
    rel, digest = source.get("raw_archive"), source.get("body_sha256")
    if not rel or not digest:
        return "SOURCE_HASH_MISSING_HOLD"
    path = base / rel
    if not path.is_file():
        return "SOURCE_RAW_BYTES_MISSING_HOLD"
    raw = gzip.decompress(path.read_bytes())
    if sha256(raw).hexdigest() != digest:
        raise ValueError("SOURCE_BYTES_SHA256_MISMATCH")
    return "SOURCE_BYTES_AND_ANCHORS_VERIFIED_PAYMENT_UNCERTIFIED"

def audit(base):
    base = Path(base)
    upstream = json.loads((base / "report.json").read_text(encoding="utf-8"))
    with (base / "unresolved_review.csv").open(newline="", encoding="utf-8") as f:
        rows = {(r["symbol"], r["ex_date"]): r for r in csv.DictReader(f)}
    events = []
    for symbol, day, sid in TARGETS:
        row = rows.get((symbol, day))
        source = upstream.get("source_results", {}).get(sid)
        evidence_status = source_status(base, source, symbol + "|" + day)
        event = {
            "symbol": symbol, "ex_date": day, "source_id": sid,
            "source_url": source.get("url") if source else None,
            "source_body_sha256": source.get("body_sha256") if source else None,
            "archived_evidence_status": evidence_status,
            "unarchived_research_leads": UNARCHIVED_LEADS[symbol],
            "actual_payment_certified": False,
            "independent_adjustment_factor_certified": False,
            "independent_close_certified": False,
            "issuer_ex_date_and_amount_jointly_certified": False,
            "research_hold": True,
        }
        if row is None:
            event["reason"] = "EVENT_NOT_IN_UPSTREAM_REVIEW_HOLD"
        else:
            if any(row.get(k) != "False" for k in (
                    "actual_payment_certified",
                    "independent_adjustment_factor_certified",
                    "independent_close_certified")):
                raise ValueError("UPSTREAM_FINALITY_UNEXPECTEDLY_PROMOTED")
            event["prior_grade"] = row.get("primary_evidence_grade")
            if symbol == "QQQ":
                quote = number(row.get("primary_amount_usd"))
                alpaca = number(row.get("alpaca_rate"))
                event.update({
                    "sec_2020_third_party_2018_q3_quote_usd": str(quote) if quote is not None else None,
                    "alpaca_2018_event_candidate_usd": str(alpaca) if alpaca is not None else None,
                    "contemporaneous_rounded_secondary_candidate_usd": "0.3764",
                    "sec_quote_minus_alpaca_usd": str(quote-alpaca) if quote is not None and alpaca is not None else None,
                    "secondary_rounded_minus_alpaca_usd": str(Decimal("0.3764")-alpaca) if alpaca is not None else None,
                    "issuer_annual_report_scope": "2018_ANNUAL_AGGREGATE_ONLY_NOT_EX_DATE",
                    "reason": "CONFLICTING_NUMERIC_CANDIDATES_UNRESOLVED_HOLD",
                })
                if quote != Decimal("0.37837"):
                    event["reason"] = "SEC_QUOTE_UNEXPECTED_HOLD"
            else:
                raw = number(row.get("third_party_raw_2023_cash_usd"))
                adjusted = number(row.get("third_party_adjusted_cash_usd"))
                ratio = number(row.get("split_new_shares_per_old"))
                consistent = ratio == Decimal("2") and raw is not None and adjusted is not None and raw/ratio == adjusted
                event.update({
                    "raw_2023_cash_candidate_usd": str(raw) if raw is not None else None,
                    "split_adjusted_cash_candidate_usd": str(adjusted) if adjusted is not None else None,
                    "split_new_shares_per_old": str(ratio) if ratio is not None else None,
                    "split_date": row.get("split_event_date"),
                    "candidate_split_math_consistent": consistent,
                    "reason": "2025_SPLIT_DOES_NOT_CERTIFY_2023_CASH_HOLD" if consistent else "SPLIT_CANDIDATE_MATH_HOLD",
                })
        events.append(event)
    return {
        "version": VERSION, "research_only": True, "production_writes": False,
        "strategy_promoted": False, "source_finality_verified": 0,
        "issuer_payments_certified": 0,
        "unarchived_research_leads_are_certified": False,
        "both_archived_sources_verified": all(
            e["archived_evidence_status"] == "SOURCE_BYTES_AND_ANCHORS_VERIFIED_PAYMENT_UNCERTIFIED"
            for e in events),
        "status": "ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD",
        "events": events,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--primary-dir", default="output/daily20/research/issuer_ca_primary")
    p.add_argument("--out", default="output/daily20/research/issuer_ca_gap_audit.json")
    args = p.parse_args()
    result = audit(args.primary_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("DAILY20_CA_GAP", result["status"], "two_source_hashes",
          result["both_archived_sources_verified"], "CERTIFIED 0/26 HOLD")

if __name__ == "__main__":
    main()
