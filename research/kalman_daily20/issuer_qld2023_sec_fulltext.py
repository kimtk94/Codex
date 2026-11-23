#!/usr/bin/env python3
"""Bounded original-text research on ProShares QLD's 2023 SEC N-CSRS.

The pinned 2023-11-30 primary-document.htm is ~71 MB. This collector reads the
entire original in bounded chunks, saves compressed exact bytes and SHA-256,
and records *unscoped text occurrences*. It DOES NOT infer event cash amounts,
nonpayment, ticker-level accounting allocations, or price factor finality.
After one verified fetch, a matching previously archived immutable accession
may be reused, with digest checked against the actual decompressed bytes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile, BadZipFile

from issuer_ca_primary_evidence import text_of_html

VERSION = "daily20-qld-2023-ncsrs-fulltext-v1"
SEC_URL = ("https://www.sec.gov/Archives/edgar/data/1174610/"
           "000200004824000003/primary-document.htm")
ARCHIVE_NAME = "qld_2023_original_full_ncsrs.htm.gz"
RESULT_FOLDER = "research/issuer_qld2023_fulltext"
MAX_RAW = 80_000_000
MAX_GZIP = 32_000_000
CHUNK = 512 * 1024
TEXT_RULES = {
    "fund_heading": r"\b(?:proshares\s+)?ultra\s+qqq\b",
    "report_period": r"november\s+30,?\s+2023",
    "sept_exdate_iso": r"2023[-/]09[-/]20",
    "sept_exdate_words": r"september\s+20,?\s+2023",
    "candidate_original_dividend": r"(?<![0-9])0\.176282(?![0-9])",
    "candidate_post_split_dividend": r"(?<![0-9])0\.088141(?![0-9])",
    "financial_highlights": r"financial\s+highlights",
    "distribution_shareholders": r"distributions?\s+to\s+shareholders",
    "distribution_net_investment": r"distributions?\s+from\s+net\s+investment\s+income",
}
REQUIRED_META = ("QLD_2023_09",
                 "SEC_FIXED_HISTORICAL_FILING_METADATA_VERIFIED_CASH_HOLD")


def failure_code(exc):
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return "TRANSPORT_ERROR"
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, ValueError):
        s = str(exc)
        if s.startswith("QLD_SEC_") and re.fullmatch("[A-Z0-9_]{8,100}",s):
            return s
    return "SOURCE_ERROR"


def check_index(index_report):
    if not isinstance(index_report, dict):
        return False
    for item in index_report.get("cases", []):
        if (item.get("source_id"), item.get("source_status")) == REQUIRED_META:
            return (item.get("metadata_identity_verified") is True
                    and item.get("underlying_report_url") == SEC_URL
                    and item.get("underlying_report_cash_ledger_examined") is False
                    and item.get("historical_issuer_event_paid_cash_certified") is False)
    return False


def get_full_document(archive_path):
    archive_path = Path(archive_path)
    if not archive_path.parent.exists():
        archive_path.parent.mkdir(parents=True)
    req = Request(SEC_URL, headers={
        "Accept": "text/html",
        "User-Agent": "KalmanDaily20ResearchEvidence/1.0",
    })
    with urlopen(req, timeout=65) as response:
        p = urlparse(response.geturl())
        if p.scheme != "https" or p.hostname != "www.sec.gov":
            raise ValueError("QLD_SEC_UNTRUSTED_REDIRECT")
        if response.status != 200:
            raise ValueError("QLD_SEC_NON_200")
        count = 0
        hasher = sha256()
        # Write a temp file alongside the destination and atomically replace
        # only after BOTH raw and compressed size limits pass.
        with NamedTemporaryFile(mode="wb", prefix=".qld-sec-", suffix=".part",
                                dir=archive_path.parent, delete=False) as tmp:
            temp = Path(tmp.name)
        try:
            with temp.open("wb") as binary, gzip.GzipFile(
                fileobj=binary, mode="wb", compresslevel=6, mtime=0) as out:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > MAX_RAW:
                        raise ValueError("QLD_SEC_ORIGINAL_TOO_LARGE")
                    hasher.update(chunk)
                    out.write(chunk)
            if count < 10_000:
                raise ValueError("QLD_SEC_ORIGINAL_UNEXPECTEDLY_SHORT")
            if temp.stat().st_size > MAX_GZIP:
                raise ValueError("QLD_SEC_COMPRESSED_ARCHIVE_TOO_LARGE")
            temp.replace(archive_path)
        finally:
            temp.unlink(missing_ok=True)
    return {"source_sha256":hasher.hexdigest(), "source_bytes":count,
            "archive_bytes":archive_path.stat().st_size,
            "source_acquisition":"LIVE_SEC_FIXED_ORIGINAL"}


def unpack_verified(archive_path, expected_digest=None):
    archive_path=Path(archive_path)
    if archive_path.stat().st_size > MAX_GZIP:
        raise ValueError("QLD_SEC_ARCHIVE_SIZE_EXCEEDED")
    with gzip.open(archive_path,"rb") as fh:
        raw=fh.read(MAX_RAW+1)
    if len(raw)>MAX_RAW or len(raw)<10_000:
        raise ValueError("QLD_SEC_RAW_SIZE_INVALID")
    digest=sha256(raw).hexdigest()
    if expected_digest is not None and expected_digest != digest:
        raise ValueError("QLD_SEC_SOURCE_DIGEST_MISMATCH")
    return raw, digest


def scan(raw):
    if len(raw)>MAX_RAW:
        raise ValueError("QLD_SEC_TOO_BIG_FOR_TEXT_SCAN")
    if not raw.lstrip()[:256].lower().startswith((b"<!doctype",b"<html",b"<head",b"<?xml")):
        raise ValueError("QLD_SEC_NOT_HTML")
    body=text_of_html(raw)
    lower=body.lower()
    matches={}
    snippets={}
    for name,pattern in TEXT_RULES.items():
        offsets=[]
        count=0
        for m in re.finditer(pattern,lower):
            count+=1
            if len(offsets)<6:
                offsets.append(m.start())
        matches[name]={"total_unscoped_hits":count,
                       "first_six_visible_text_offsets":offsets}
        # Snippets are *public SEC text*, capped and not independently
        # interpreted as QLD-specific accounting line items.
        snippets[name]=[
            body[max(0,i-180):min(len(body),i+220)] for i in offsets[:3]
        ]
    identifiable=(matches["fund_heading"]["total_unscoped_hits"]>0
                  and matches["report_period"]["total_unscoped_hits"]>0
                  and matches["financial_highlights"]["total_unscoped_hits"]>0)
    return {
        "source_text_length":len(body),
        "document_anchors_present":identifiable,
        "unscoped_full_filing_text_term_counts":matches,
        "bounded_unscoped_source_snippets":snippets,
        "text_evidence_scope":"FULL_TRUST_REPORT_NOT_QLD_EVENT_PAYMENT_LEDGER",
        "september_payment_certified":False,
        "fund_specific_payment_allocation_certified":False,
    }


def restore_immutable_cache(previous_zip, destination):
    if not previous_zip or not Path(previous_zip).is_file():
        return None
    try:
        with ZipFile(previous_zip) as z:
            member=RESULT_FOLDER+"/"+ARCHIVE_NAME
            meta=RESULT_FOLDER+"/report.json"
            if member not in z.namelist() or meta not in z.namelist():
                return None
            report=json.loads(z.read(meta))
            if (report.get("version")!=VERSION
                    or report.get("source_url")!=SEC_URL
                    or report.get("source_archive")!=ARCHIVE_NAME
                    or not report.get("document_anchors_present")
                    or not report.get("source_sha256")
                    or report.get("issuer_event_cash_certified") is not False):
                return None
            info=z.getinfo(member)
            if info.file_size>MAX_GZIP:
                return None
            archive=z.read(member)
            destination.write_bytes(archive)
        raw,digest=unpack_verified(destination,report["source_sha256"])
        return {"source_sha256":digest,"source_bytes":len(raw),
                "archive_bytes":len(archive),
                "source_acquisition":"VERIFIED_IMMUTABLE_PRIOR_ARCHIVE"}
    except (OSError,ValueError,KeyError,BadZipFile,gzip.BadGzipFile):
        destination.unlink(missing_ok=True)
        return None


def collect(*, offline=False, index_report=None, out_dir=None,
            previous_zip=None, fetcher=get_full_document):
    path=Path(out_dir or "output/daily20/research/issuer_qld2023_fulltext")
    path.mkdir(parents=True,exist_ok=True)
    out={
        "version":VERSION,"research_only":True,
        "production_writes":False,"strategy_promoted":False,
        "source_url":SEC_URL,"underlying_sec_accession":"0002000048-24-000003",
        "source_archive":None,"source_sha256":None,"source_bytes":None,
        "source_acquisition":None,"source_text_length":None,
        "document_anchors_present":False,"source_failure_code":None,
        "issuer_event_cash_certified":False,"historical_nonpayment_proven":False,
        "independent_price_adjustment_factor_certified":False,
        "source_finality_verified_assets":0,
        "status":"OFFLINE_NO_SEC_FULLTEXT_HOLD" if offline else "SEC_FULLTEXT_PENDING_HOLD",
    }
    archive=path/ARCHIVE_NAME
    if offline:
        return out
    if not check_index(index_report):
        out.update(status="SEC_INDEX_UNVERIFIED_FULLTEXT_HOLD",
                   source_failure_code="QLD_SEC_INDEX_NOT_CERTIFIED")
        return out
    try:
        metadata=restore_immutable_cache(previous_zip,archive)
        if metadata is None:
            metadata=fetcher(archive)
        raw,digest=unpack_verified(archive,metadata["source_sha256"])
        if digest != metadata["source_sha256"]:
            raise ValueError("QLD_SEC_SOURCE_DIGEST_MISMATCH")
        findings=scan(raw)
        out.update(metadata)
        out.update(findings)
        out["source_archive"]=ARCHIVE_NAME
        out["status"]=("SEC_FULLTEXT_SCANNED_UNSCOPED_PAYMENT_HOLD"
                       if findings["document_anchors_present"]
                       else "SEC_FULLTEXT_ANCHORS_MISSING_HOLD")
    except (OSError,ValueError,URLError,HTTPError,TimeoutError,
            UnicodeDecodeError,gzip.BadGzipFile) as exc:
        out["status"]="SEC_FULLTEXT_FETCH_OR_VALIDATE_FAILED_HOLD"
        out["source_failure_code"]=failure_code(exc)
        if not archive.exists():
            out["source_archive"]=None
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--index",default="output/daily20/research/issuer_historical_edgar/report.json")
    p.add_argument("--out-dir",default="output/daily20/research/issuer_qld2023_fulltext")
    p.add_argument("--previous-results",default="output/daily20/previous-results.zip")
    p.add_argument("--offline",action="store_true")
    args=p.parse_args()
    src=json.loads(Path(args.index).read_text()) if Path(args.index).is_file() else {}
    result=collect(offline=args.offline,index_report=src,out_dir=args.out_dir,
                   previous_zip=args.previous_results)
    (Path(args.out_dir)/"report.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("DAILY20_SEC_QLD2023_FULLTEXT",result["status"],
          "acquisition",result["source_acquisition"],
          "bytes",result["source_bytes"],
          "failure",result["source_failure_code"],
          "cash_certified",result["issuer_event_cash_certified"])

if __name__=="__main__":
    main()
