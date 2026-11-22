#!/usr/bin/env python3
"""Read-only first-party FY2018 QQQ annual distribution aggregate evidence.

The original SEC-filed issuer annual report gives total fiscal-year distributions,
NOT the distribution attributable to 2018-06-18. Preserve original bytes and
keep the single-date event amount and price-adjustment factor on HOLD.
"""
from __future__ import annotations

import argparse
import gzip
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SOURCE_URL = ("https://www.sec.gov/Archives/edgar/data/1067839/"
              "000119312518355790/d638310dn30b2.htm")
VERSION = "daily20-qqq2018-firstparty-fiscal-evidence-v1"
MAX_BYTES = 6_000_000
TARGET_EX_DATE = "2018-06-18"
FISCAL_END = "2018-09-30"


def fetch_original(url=SOURCE_URL):
    if url != SOURCE_URL:
        raise ValueError("QQQ_FY_SOURCE_URL_NOT_PINNED")
    request = Request(url, headers={
        "Accept": "text/html",
        "User-Agent": "KalmanIssuerHistoricalEvidence/1.0",
    })
    with urlopen(request, timeout=30) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "www.sec.gov":
            raise ValueError("QQQ_FY_SOURCE_UNTRUSTED_REDIRECT")
        if response.status != 200:
            raise ValueError("QQQ_FY_SOURCE_BAD_HTTP_STATUS")
        raw = response.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("QQQ_FY_EMPTY_OR_OVERSIZE")
    return raw


def normalized_html(raw):
    if not isinstance(raw, bytes):
        raise ValueError("QQQ_FY_RAW_NOT_BYTES")
    doc = raw.decode("utf-8-sig", errors="replace")
    doc = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?s)<[^>]+>", " ", doc)
    return " ".join(unescape(doc).split())


def verify_document(raw):
    """Match the FY2018 column and its specific 'Net investment income' row.

    Never infer the single-date payout as a quarter of the annual figure.
    A number 1.31 elsewhere in the report is insufficient.
    """
    doc = normalized_html(raw)
    trust = bool(re.search(r"Invesco QQQ Trust", doc, re.I))
    patterns = (
        r"Financial Highlights.{0,2200}?Year Ended September\s*30,?\s*2018\s+2017\s+2016",
        r"Distributions to Shareholders from:\s*Net investment income\s*\(?\s*1\.31\b",
    )
    header = None
    for match in re.finditer(patterns[0], doc, re.I | re.S):
        section = doc[match.end():match.end() + 4500]
        if re.search(patterns[1], section, re.I | re.S):
            header = match
            break
    return {
        "issuer_trust_name_observed": trust,
        "fy2018_financial_highlights_row_verified": bool(trust and header),
        "fy2018_distributions_per_share_usd": "1.31" if trust and header else None,
        "source_sha256": sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "source_text_sha256": sha256(doc.encode()).hexdigest(),
    }


def audit(*, offline=False, getter=fetch_original, out_dir=None):
    report = {
        "schema": VERSION, "research_only": True,
        "production_writes": False, "strategy_promoted": False,
        "source_url": SOURCE_URL,
        "source_provenance": "ISSUER_FILED_SEC_FISCAL_ANNUAL_REPORT",
        "report_fiscal_year_end": FISCAL_END,
        "case_ex_date": TARGET_EX_DATE,
        "source_sha256": None, "source_bytes": None,
        "source_text_sha256": None, "original_html_gzip": None,
        "issuer_trust_name_observed": False,
        "fy2018_financial_highlights_row_verified": False,
        "fy2018_distributions_per_share_usd": None,
        "fiscal_total_is_event_payment_amount": False,
        "qqq_2018_06_18_specific_cash_usd_certified": None,
        "issuer_single_event_amount_certified": False,
        "independent_adjustment_factor_certified": False,
        "independent_close_certified": False,
        "source_finality_verified": 0,
        "status": "PR_OFFLINE_NO_FIRST_PARTY_REPORT_HOLD" if offline
                  else "FIRST_PARTY_FY_SOURCE_PENDING_HOLD",
        "error_code": None,
    }
    if offline:
        return report
    try:
        raw = getter(SOURCE_URL)
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
            raise ValueError("QQQ_FY_SOURCE_BYTES_INVALID")
        evidence = verify_document(raw)
        report.update(evidence)
        if out_dir is not None:
            path = Path(out_dir)
            path.mkdir(parents=True, exist_ok=True)
            dest = path / "qqq_fiscal_2018_original_sec_annual.html.gz"
            dest.write_bytes(gzip.compress(raw, mtime=0))
            if sha256(gzip.decompress(dest.read_bytes())).hexdigest() != evidence["source_sha256"]:
                raise ValueError("QQQ_FY_ARCHIVE_HASH_MISMATCH")
            report["original_html_gzip"] = dest.name
        report["status"] = (
            "ISSUER_FY2018_AGGREGATE_VERIFIED_20180618_CASH_HOLD"
            if evidence["fy2018_financial_highlights_row_verified"]
            else "ISSUER_FY2018_ROW_NOT_VERIFIED_HOLD"
        )
    except (OSError, ValueError, TimeoutError, UnicodeError) as exc:
        report["status"] = "ISSUER_FY2018_SOURCE_OR_ARCHIVE_ERROR_HOLD"
        # Never expose raw remote response text, URLs or exception payload.
        code = str(exc)
        report["error_code"] = (
            code if re.fullmatch(r"QQQ_FY_[A-Z0-9_]{3,80}", code)
            else type(exc).__name__
        )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="output/daily20/research/issuer_qqq2018_fiscal")
    parser.add_argument("--offline", action="store_true")
    opts = parser.parse_args()
    dest = Path(opts.out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    report = audit(offline=opts.offline, out_dir=dest)
    (dest / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("DAILY20_QQQ2018_FISCAL", report["status"],
          "fy_per_share", report["fy2018_distributions_per_share_usd"],
          "single_event_cash_certified", report["issuer_single_event_amount_certified"],
          "FINALITY_HOLD 0/26")


if __name__ == "__main__":
    main()
