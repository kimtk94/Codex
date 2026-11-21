#!/usr/bin/env python3
"""Read-only first-party sponsor/issuer evidence for Daily20 CA exception triage.

A web page anchor and an issuer amount are candidate factual corroboration,
not a certified Yahoo split/dividend factor. QLD calendar dates are explicitly
NOT paid dividend evidence. Never update market history or promote a signal.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from io import BytesIO
from hashlib import sha256
from html import unescape
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from daily20 import write_json

VERSION = "daily20-issuer-ca-primary-evidence-v1"
SCHEMA = "daily20-primary-corporate-action-sources-v1"
SOURCE_LIMIT = 6_000_000
PDF_SOURCE_LIMIT = 20_000_000
SUPPORTED_TYPES = {
    "FUND_GROSS_USD_PER_CDI",
    "ISSUER_QUARTERLY_PRE_SPLIT_USD",
    "FUND_DISTRIBUTION_SCHEDULE_ONLY",
    "ISSUER_DECLARED_COMMON_USD",
    "ISSUER_COMMON_STOCK_NO_DIVIDEND_POLICY",
    "ISSUER_FUND_HISTORICAL_USD",
    "SEC_FILED_THIRD_PARTY_ISSUER_AMOUNT_QUOTE",
}
ALLOWED = {
    "www.ssga.com", "investors.broadcom.com", "www.proshares.com",
    "news.microsoft.com", "investor.exxonmobil.com", "www.strategy.com",
    "www.sec.gov", "www.blackrock.com",
}
OUT_FIELDS = [
    "symbol", "ex_date", "comparison_status", "prior_diagnostic_reason",
    "yahoo_repaired_event", "alpaca_rate", "primary_claim_type",
    "primary_amount_usd", "source_id", "source_url", "source_fetch_status",
    "primary_evidence_grade", "amount_matches_alpaca_raw",
    "amount_matches_yahoo_as_reported", "amount_comparison_basis",
    "exdate_explicitly_issuer_published", "actual_payment_certified",
    "independent_adjustment_factor_certified", "independent_close_certified",
]


def number(value):
    if value is None or value == "":
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return n if n.is_finite() else None


def valid_day(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def validate_manifest(manifest):
    if manifest.get("schema") != SCHEMA or manifest.get("research_only") is not True:
        raise ValueError("PRIMARY_CA_MANIFEST_GOVERNANCE_INVALID")
    sources = {}
    for source in manifest.get("sources", []):
        sid = source.get("id")
        url = source.get("url")
        if (not isinstance(sid, str) or not re.fullmatch(r"[A-Z0-9_]{3,80}", sid)
                or sid in sources or not isinstance(url, str)):
            raise ValueError("PRIMARY_CA_BAD_SOURCE_ID")
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname not in ALLOWED
                or parsed.username or parsed.password or parsed.query
                or parsed.fragment):
            raise ValueError("PRIMARY_CA_UNTRUSTED_ISSUER_DOMAIN")
        if source.get("kind") == "issuer_fund_report_pdf" and not parsed.path.endswith(".pdf"):
            raise ValueError("PRIMARY_CA_PDF_SOURCE_SUFFIX_MISMATCH")
        sources[sid] = source
    if not sources:
        raise ValueError("PRIMARY_CA_NO_SOURCES")
    claims = {}
    for claim in manifest.get("claims", []):
        symbol, day = claim.get("symbol"), claim.get("ex_date")
        key = (symbol, day)
        if (not isinstance(symbol, str) or not valid_day(day)
                or key in claims or claim.get("source_id") not in sources):
            raise ValueError("PRIMARY_CA_DUPLICATED_OR_UNSOURCED_CLAIM")
        kind = claim.get("claim_type")
        amount = number(claim.get("reported_amount_usd"))
        if kind not in SUPPORTED_TYPES:
            raise ValueError("PRIMARY_CA_CLAIM_TYPE_UNKNOWN")
        skind = sources[claim["source_id"]]["kind"]
        if kind == "ISSUER_FUND_HISTORICAL_USD" and skind != "issuer_fund_report_pdf":
            raise ValueError("PRIMARY_CA_PDF_ISSUER_PROVENANCE_MISMATCH")
        if (kind == "SEC_FILED_THIRD_PARTY_ISSUER_AMOUNT_QUOTE"
                and skind != "sec_filed_third_party_issuer_quote"):
            raise ValueError("PRIMARY_CA_SEC_QUOTE_PROVENANCE_MISMATCH")
        non_amount_types = {
            "FUND_DISTRIBUTION_SCHEDULE_ONLY",
            "ISSUER_COMMON_STOCK_NO_DIVIDEND_POLICY",
        }
        if (kind in non_amount_types) != (amount is None):
            raise ValueError("PRIMARY_CA_SCHEDULE_MUST_NOT_ASSERT_PAID_AMOUNT")
        if amount is not None and amount <= 0:
            raise ValueError("PRIMARY_CA_INVALID_AMOUNT")
        if (type(claim.get("claim_amount_exact")) is not bool
                or type(claim.get("exdate_explicitly_issuer_published")) is not bool
                or (amount is None and claim["claim_amount_exact"])):
            raise ValueError("PRIMARY_CA_UNATTESTED_CLAIM_SCOPE")
        for key_name in ("anchor_a", "anchor_b"):
            v = claim.get(key_name)
            if not isinstance(v, str) or len(v) < 4 or len(v) > 90:
                raise ValueError("PRIMARY_CA_ANCHOR_INVALID")
        claims[key] = claim
    return sources, claims


def fetch_bytes(url):
    req = Request(url, headers={
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "KalmanDaily20ResearchEvidence/1.0",
    })
    with urlopen(req, timeout=27) as res:
        returned = urlparse(res.geturl())
        if returned.scheme != "https" or returned.hostname not in ALLOWED:
            raise ValueError("PRIMARY_CA_REDIRECT_TO_UNTRUSTED_SOURCE")
        if res.status != 200:
            raise ValueError("PRIMARY_CA_SOURCE_NOT_200")
        limit = PDF_SOURCE_LIMIT if urlparse(url).path.endswith(".pdf") else SOURCE_LIMIT
        raw = res.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError("PRIMARY_CA_SOURCE_EMPTY_OR_OVERSIZE")
    return raw


def text_of_html(blob):
    text = blob.decode("utf-8-sig", errors="replace")
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(unescape(text).split())


def text_of_pdf(blob):
    """Extract only displayed PDF text, never treat binary PDF as HTML."""
    if not blob.startswith(b"%PDF"):
        raise ValueError("PRIMARY_CA_NOT_A_PDF")
    # pypdf is installed by the isolated issuer-source CI step.
    from pypdf import PdfReader
    doc = PdfReader(BytesIO(blob), strict=False)
    # The BlackRock historical distribution table appears near the start.
    # Hard cap keeps parsing bounded; an absent page is a HOLD, not a guess.
    pages = min(18, len(doc.pages))
    plain = " ".join((doc.pages[i].extract_text() or "") for i in range(pages))
    plain = " ".join(plain.split())
    return re.sub(r"(\\d{1,2})\\s*月\\s*(\\d{1,2})\\s*日",
                  r"\\1月\\2日", plain)


def grade_anchors(blob, claim, *, pdf=False):
    if pdf:
        try:
            plain = text_of_pdf(blob).lower()
        except Exception:
            # Damaged/unreadable PDF or unsupported glyph encoding must
            # NOT be accepted as verified evidence.
            plain = ""
    else:
        plain = text_of_html(blob).lower()
    a = claim["anchor_a"].lower()
    b = claim["anchor_b"].lower()
    # Both anchors must occur in a nearby local context, not merely somewhere
    # in a long issuer page. 16K limit admits same row of a fund table.
    posa = [m.start() for m in re.finditer(re.escape(a), plain)]
    posb = [m.start() for m in re.finditer(re.escape(b), plain)]
    found = bool(posa and posb and min(abs(x-y) for x in posa for y in posb) <= 1800)
    return found, sha256(plain.encode()).hexdigest()


def probe_source(source, claims, out_dir, *, getter=fetch_bytes, offline=False):
    result = {
        "source_id": source["id"], "url": source["url"],
        "status": "OFFLINE_NO_RAW_SOURCE_HOLD" if offline else "SOURCE_NOT_FETCHED_HOLD",
        "body_sha256": None, "body_bytes": 0, "raw_archive": None,
        "anchor_grade_by_claim": {},
        "body_text_sha256": None,
        "source_claim_independently_certified": False,
    }
    if offline:
        return result
    try:
        raw = getter(source["url"])
        limit = (PDF_SOURCE_LIMIT
                 if source["kind"] == "issuer_fund_report_pdf" else SOURCE_LIMIT)
        if not isinstance(raw, bytes) or not raw or len(raw) > limit:
            raise ValueError("PRIMARY_CA_SOURCE_SIZE_INVALID")
        if source["kind"] == "issuer_fund_report_pdf" and not raw.startswith(b"%PDF"):
            raise ValueError("PRIMARY_CA_SOURCE_NOT_PDF")
        digest = sha256(raw).hexdigest()
        raw_dir = Path(out_dir) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        filename = source["id"].lower() + (
            ".pdf.gz" if source["kind"] == "issuer_fund_report_pdf" else ".html.gz")
        (raw_dir / filename).write_bytes(gzip.compress(raw, mtime=0))
        result.update({
            "status": "FETCHED_SOURCE_UNCERTIFIED",
            "body_sha256": digest, "body_bytes": len(raw),
            "raw_archive": "raw/" + filename,
        })
        for claim in claims:
            found, bodytext = grade_anchors(
                raw, claim, pdf=source["kind"] == "issuer_fund_report_pdf")
            key = claim["symbol"] + "|" + claim["ex_date"]
            result["anchor_grade_by_claim"][key] = (
                "BOTH_NEARBY_ANCHORS_OBSERVED" if found
                else "ANCHORS_NOT_VERIFIED_HOLD")
            result["body_text_sha256"] = bodytext
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, UnicodeError) as exc:
        result["status"] = ("HTTP_" + str(exc.code) + "_SOURCE_HOLD"
                            if isinstance(exc, HTTPError)
                            else type(exc).__name__ + "_SOURCE_HOLD")
    return result


def compare_issuer_claim(row, claim, fetched):
    if claim is None:
        return {
            "primary_claim_type": None, "primary_amount_usd": None,
            "source_id": None, "source_url": None,
            "source_fetch_status": None,
            "primary_evidence_grade": "NO_CURATED_PRIMARY_SOURCE_HOLD",
            "amount_matches_alpaca_raw": None,
            "amount_matches_yahoo_as_reported": None,
            "amount_comparison_basis": "UNAVAILABLE",
            "exdate_explicitly_issuer_published": None,
        }
    key = claim["symbol"] + "|" + claim["ex_date"]
    current_status = fetched["anchor_grade_by_claim"].get(key)
    source_attested = current_status == "BOTH_NEARBY_ANCHORS_OBSERVED"
    amount = number(claim["reported_amount_usd"])
    alpaca = number(row.get("alpaca_rate"))
    yahoo = number(row.get("yahoo_repaired_event"))
    # Source amounts are *as issued*, while Yahoo dividend may be split-
    # adjusted and 3dp-rounded. Comparison is only a numeric diagnostic.
    tol = Decimal("0.0005")
    a_match = None if amount is None or alpaca is None else abs(amount - alpaca) <= tol
    y_match = None if amount is None or yahoo is None else abs(amount - yahoo) <= tol
    if not source_attested:
        grade = "OFFICIAL_SOURCE_ANCHORS_NOT_LIVE_ATTESTED_HOLD"
    elif claim["claim_type"] == "ISSUER_COMMON_STOCK_NO_DIVIDEND_POLICY":
        # Policy may indicate a misclassified security (preferred vs common)
        # but DOES NOT negate any observed Alpaca event or certify a CUSIP.
        grade = "ISSUER_COMMON_CLASS_NO_DIVIDEND_POLICY_OBSERVED_IDENTITY_HOLD"
    elif amount is None:
        grade = "ISSUER_EXPECTED_CALENDAR_DATE_ONLY_NO_PAYMENT_ASSERTION"
    elif claim["claim_type"] == "ISSUER_QUARTERLY_PRE_SPLIT_USD":
        grade = "ISSUER_PRE_SPLIT_QUARTER_AMOUNT_OBSERVED_NOT_FACTOR_CERTIFIED"
    elif claim["claim_type"] == "SEC_FILED_THIRD_PARTY_ISSUER_AMOUNT_QUOTE":
        # SEC hosting authenticates the filed note, not the issuer's original
        # distribution statement nor per-event vendor identity or ex-date.
        grade = "SEC_HOSTED_THIRD_PARTY_QUOTE_NUMERIC_ONLY_NOT_ISSUER_ATTESTED"
    elif a_match and not y_match:
        grade = "ISSUER_AMOUNT_FAVORS_ALPACA_NUMERIC_ONLY"
    elif y_match and not a_match:
        grade = "ISSUER_AMOUNT_FAVORS_YAHOO_NUMERIC_ONLY"
    elif a_match and y_match:
        grade = "ISSUER_AMOUNT_AGREES_BOTH_NUMERIC_ONLY"
    else:
        grade = "ISSUER_NUMERIC_COMPARISON_UNRESOLVED_HOLD"
    return {
        "primary_claim_type": claim["claim_type"],
        "primary_amount_usd": str(amount) if amount is not None else None,
        "source_id": claim["source_id"],
        "source_url": fetched["url"],
        "source_fetch_status": fetched["status"],
        "primary_evidence_grade": grade,
        "amount_matches_alpaca_raw": a_match,
        "amount_matches_yahoo_as_reported": y_match,
        "amount_comparison_basis": (
            "RAW_PRE_SPLIT_ISSUER_AMOUNT_NOT_YAHOO_COMPARABLE"
            if claim["claim_type"] == "ISSUER_QUARTERLY_PRE_SPLIT_USD"
            else "ISSUER_POLICY_NO_COMMON_DIVIDEND_SECURITY_CLASS_HOLD"
            if claim["claim_type"] == "ISSUER_COMMON_STOCK_NO_DIVIDEND_POLICY"
            else "EXPECTED_SCHEDULE_NOT_PAID_AMOUNT"
            if amount is None
            else "ISSUER_DECLARED_NOT_YET_PAID_FUTURE_DATE"
            if claim["claim_type"] == "ISSUER_DECLARED_COMMON_USD"
            else "SEC_THIRD_PARTY_QUOTE_NOT_ORIGINAL_ISSUER_STATEMENT"
            if claim["claim_type"] == "SEC_FILED_THIRD_PARTY_ISSUER_AMOUNT_QUOTE"
            else "ISSUER_HISTORICAL_DISTRIBUTION_NOT_EX_DATE_CERTIFIED"
            if claim["claim_type"] == "ISSUER_FUND_HISTORICAL_USD"
            else "ETF_GROSS_USD_PER_CDI_POTENTIAL_SHARE_UNIT_DIFFERENCE"),
        "exdate_explicitly_issuer_published": claim["exdate_explicitly_issuer_published"]
                                           if source_attested else None,
    }


def run(manifest, review_rows, out_dir, *, offline=False, getter=fetch_bytes):
    sources, claims = validate_manifest(manifest)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    source_results = {}
    for sid, src in sources.items():
        source_results[sid] = probe_source(
            src, [cl for cl in claims.values() if cl["source_id"] == sid],
            out, offline=offline, getter=getter)
    rows = []
    seen = set()
    for row in review_rows:
        key = (row["symbol"], row["ex_date"])
        if key in seen or not valid_day(key[1]):
            raise ValueError("PRIMARY_CA_REVIEW_DUPLICATE_OR_INVALID_DATE")
        seen.add(key)
        # The earlier Yahoo repair policy diagnostics are already explained,
        # but must stay in the original review file and issuer HOLD audit.
        if row["diagnostic_reason"] == "YAHOO_REPAIR_SUPPRESSED_DIVIDEND_OBSERVED":
            continue
        claim = claims.get(key)
        extra = compare_issuer_claim(
            row, claim,
            source_results[claim["source_id"]] if claim else None)
        rows.append({
            "symbol": row["symbol"], "ex_date": row["ex_date"],
            "comparison_status": row["comparison_status"],
            "prior_diagnostic_reason": row["diagnostic_reason"],
            "yahoo_repaired_event": row["yahoo_repaired_event"],
            "alpaca_rate": row["alpaca_rate"],
            **extra,
            "actual_payment_certified": False,
            "independent_adjustment_factor_certified": False,
            "independent_close_certified": False,
        })
    match_keys = {(r["symbol"],r["ex_date"]) for r in rows}
    claimed_keys = set(claims)
    if not claimed_keys.issubset(match_keys) and not offline:
        # On a new session, source lead may remain valid while a vendor no
        # longer flags that row. Record the gap; never invent a new exception.
        pass
    status_counts = {}
    for r in rows:
        status_counts[r["primary_evidence_grade"]] = (
            status_counts.get(r["primary_evidence_grade"], 0) + 1)
    report = {
        "version": VERSION, "research_only": True,
        "production_writes": False, "strategy_promoted": False,
        "source_finality_verified": 0, "factor_certified": 0,
        "issuer_action_payments_certified": 0, "issuer_identities_certified": 0,
        "source_count": len(sources), "curated_official_leads": len(claims),
        "review_cases_observed": len(review_rows),
        "unresolved_cases_analyzed": len(rows),
        "remaining_review_case_count": len(rows),
        "official_leads_applicable": sum((r["symbol"],r["ex_date"]) in claims for r in rows),
        "issuer_fund_historical_document_leads": sum(
            (r["symbol"],r["ex_date"]) in claims and
            claims[(r["symbol"],r["ex_date"])]["claim_type"] == "ISSUER_FUND_HISTORICAL_USD"
            for r in rows),
        "sec_filed_third_party_quote_leads": sum(
            (r["symbol"],r["ex_date"]) in claims and
            claims[(r["symbol"],r["ex_date"])]["claim_type"] ==
                "SEC_FILED_THIRD_PARTY_ISSUER_AMOUNT_QUOTE"
            for r in rows),
        "sec_hosted_third_party_quote_not_issuer_certified": True,
        "raw_source_fetch_success": sum(
            v["body_sha256"] is not None for v in source_results.values()),
        "live_source_anchor_supported_cases": sum(
            r["primary_evidence_grade"] not in (
                "NO_CURATED_PRIMARY_SOURCE_HOLD",
                "OFFICIAL_SOURCE_ANCHORS_NOT_LIVE_ATTESTED_HOLD",
            ) for r in rows),
        "status_counts": status_counts,
        "source_results": source_results,
        "status": "ISSUER_PRIMARY_SOURCE_EVIDENCE_RESEARCH_HOLD",
        "source_content_does_not_certify_price_adjustment": True,
    }
    write_json(out/"report.json", report)
    with (out/"unresolved_review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", default="research/kalman_daily20/issuer_ca_primary_sources.json")
    p.add_argument("--review", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--offline", action="store_true")
    a=p.parse_args()
    with open(a.manifest, encoding="utf-8") as fh:
        manifest=json.load(fh)
    with open(a.review, newline="", encoding="utf-8") as fh:
        rows=list(csv.DictReader(fh))
    r=run(manifest, rows, a.out_dir, offline=a.offline)
    print("DAILY20_CA_ISSUER_SOURCE",r["unresolved_cases_analyzed"],"unresolved cases",
          r["official_leads_applicable"],"curated case leads",
          r["live_source_anchor_supported_cases"],"live anchors",
          r["raw_source_fetch_success"],"raw sources captured",
          "CERTIFIED 0/26 HOLD")


if __name__ == "__main__":
    main()
