#!/usr/bin/env python3
"""Immutable SEC accession provenance for QLD 2023 / QQQ 2018 (research-only).

Critical distinction: a 2023-11-30 SEC filing index confirms the existence
and identity of its *financial report*, not an ex-dated September payment.
A current ProShares 'semiannual_qld.pdf' alias is mutable and MUST NOT be
treated as the archived 2023 report. QQQ annual report is also aggregate
disclosure rather than a specific 2018-06-18 payout ledger.
"""
from __future__ import annotations

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from issuer_ca_primary_evidence import fetch_bytes, text_of_html

VERSION = "daily20-historical-edgar-fixed-accessions-v1"
CASES = {
    "QLD_2023_09": {
        "symbol": "QLD",
        "event_ex_date": "2023-09-20",
        "url": "https://www.sec.gov/Archives/edgar/data/1174610/000200004824000003/0002000048-24-000003-index.html",
        "archive": "qld_2023_ncsrs_edgar_index.html.gz",
        "required": ("0002000048-24-000003", "2024-02-05",
                     "2023-11-30", "ProShares Ultra QQQ",
                     "C000018465", "primary-document.htm"),
        "evidence_scope": "2023_11_30_NCSRS_ACCESSION_AND_QLD_FUND_ID_ONLY",
        "underlying_report_url": "https://www.sec.gov/Archives/edgar/data/1174610/000200004824000003/primary-document.htm",
        "underlying_report_bytes_claimed_by_index": 71373267,
        "underlying_report_cash_ledger_examined": False,
    },
    "QQQ_2018_06": {
        "symbol": "QQQ",
        "event_ex_date": "2018-06-18",
        "url": "https://www.sec.gov/Archives/edgar/data/1067839/000119312518355790/d638310dn30b2.htm",
        "archive": "qqq_2018_sec_issuer_annual_report.html.gz",
        "required": ("September 30, 2018", "2018 Annual Report to Shareholders",
                     "Invesco QQQ Trust", "The Bank of New York Mellon"),
        "evidence_scope": "2018_ISSUER_ANNUAL_AGGREGATE_NOT_EVENT_AMOUNT",
        "underlying_report_url": None,
        "underlying_report_bytes_claimed_by_index": None,
        "underlying_report_cash_ledger_examined": False,
    }
}
DYNAMIC_ALIAS = "https://www.proshares.com/globalassets/proshares/documents/semi-annual-reports/semiannual_qld.pdf"

def verify(source_id: str, raw: bytes):
    case = CASES[source_id]
    if not raw or len(raw) > 2_000_000:
        raise ValueError("HISTORICAL_EDGAR_SOURCE_EMPTY_OR_OVERSIZE")
    visible = text_of_html(raw).lower()
    # SEC index includes tabular date and filing metadata; never infer
    # issuer event cash or 2018/2023 share units from these anchors.
    anchors = {a: a.lower() in visible for a in case["required"]}
    return {
        "source_sha256": sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "required_anchors_present": anchors,
        "metadata_identity_verified": all(anchors.values()),
    }

def collect(*, offline=False, getter=fetch_bytes, out_dir=None):
    output = {
        "version": VERSION, "research_only": True,
        "production_writes": False, "strategy_promoted": False,
        "issuer_cash_payment_certified": False,
        "historical_nonpayment_proven": False,
        "independent_adjustment_factor_certified": False,
        "source_finality_verified_assets": 0,
        "mutable_pdf_alias": DYNAMIC_ALIAS,
        "mutable_pdf_historical_certification": False,
        "mutable_pdf_policy": "DO_NOT_USE_DYNAMIC_LATEST_PDF_AS_2023_ORIGINAL",
        "status": "HISTORICAL_EDGAR_METADATA_RESEARCH_HOLD",
        "cases": [],
    }
    folder=Path(out_dir) if out_dir is not None else None
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
    for source_id, case in CASES.items():
        row={
            "source_id": source_id, "symbol":case["symbol"],
            "event_ex_date":case["event_ex_date"],
            "url":case["url"],"evidence_scope":case["evidence_scope"],
            "underlying_report_url":case["underlying_report_url"],
            "underlying_report_bytes_claimed_by_index":case["underlying_report_bytes_claimed_by_index"],
            "underlying_report_cash_ledger_examined":False,
            "historical_issuer_event_paid_cash_certified":False,
            "source_status":"OFFLINE_SOURCE_NOT_FETCHED_HOLD" if offline else "FETCH_PENDING_HOLD",
            "source_sha256":None,"source_archive":None,
            "source_bytes":None, "metadata_identity_verified":False,
            "required_anchors_present":{}, "fetch_error_type":None,
        }
        if not offline:
            try:
                raw = getter(case["url"])
                facts=verify(source_id,raw)
                row.update(facts)
                row["source_status"]=(
                    "SEC_FIXED_HISTORICAL_FILING_METADATA_VERIFIED_CASH_HOLD"
                    if facts["metadata_identity_verified"] else
                    "SEC_FIXED_FILING_ANCHORS_INCOMPLETE_HOLD")
                if folder is not None:
                    name=case["archive"]
                    (folder/name).write_bytes(gzip.compress(raw,mtime=0))
                    row["source_archive"]=name
            except (OSError, ValueError, TimeoutError, UnicodeDecodeError) as exc:
                row["source_status"]="SEC_FIXED_FILING_FETCH_OR_PARSE_FAILED_HOLD"
                row["fetch_error_type"]=type(exc).__name__
        output["cases"].append(row)
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",default="output/daily20/research/issuer_historical_edgar")
    p.add_argument("--offline",action="store_true")
    a=p.parse_args()
    r=collect(offline=a.offline,out_dir=a.out_dir)
    folder=Path(a.out_dir)
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"report.json").write_text(json.dumps(r,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("DAILY20_HISTORICAL_EDGAR_HOLD",
          [(c["source_id"],c["source_status"]) for c in r["cases"]], "CASH_CERTIFIED 0")
if __name__ == "__main__":
    main()
