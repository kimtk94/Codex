#!/usr/bin/env python3
"""One-off, read-only audit of Nov-20 Daily20 vs public regular/after-hours quotes.

Sources below are research evidence captured on 2026-11-21; not a live API,
not independently licensed consolidated-tape data, and NOT an authority for
future sessions. Never rewrites research archives, frozen signals or LIVE.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from zipfile import ZipFile

# All closes in USD, regular U.S. session of 2026-11-20 (4pm EST).
# Each consensus figure is corroborated by >=2 distinct published websites.
REGULAR = {
    "SPY": (689.81, (
        "https://markets.ft.markitdigital.com/data/etfs/tearsheet/historical?s=SPY%3APCQ%3AUSD",
        "https://stockanalysis.com/etf/spy/history/",
        "https://twelvedata.com/markets/568728/etf/nyse/spy/historical-data")),
    "QQQ": (608.45, (
        "https://stockanalysis.com/etf/qqq/history/",
        "https://kwwl.marketminute.com/quote/NQ%3AQQQ/historical")),
    "QLD": (63.52, (
        "https://twelvedata.com/markets/734028/etf/nyse/qld/historical-data",
        "https://www.investing.com/etfs/proshares-ultra-qqq-etf-historical-data")),
    "NVDA": (125.53, (
        "https://markets.ft.markitdigital.com/data/equities/tearsheet/historical?s=NVDA%3ANSQ",
        "https://stockanalysis.com/stocks/nvda/history/")),
    "IONQ": (20.72, (
        "https://investors.ionq.com/stock-info/",
        "https://stockanalysis.com/stocks/ionq/history/")),
    "LQD": (103.69, (
        "https://twelvedata.com/markets/101807/etf/nyse/lqd/historical-data",
        "https://www.financialcontent.com/quote/NY%3ALQD/historical")),
    "TLT": (81.45, (
        "https://twelvedata.com/markets/333615/etf/nasdaq/tlt/historical-data",
        "https://finabase.io/symbol/tlt/history")),
}

# Source label/type is essential: "after hours" != final regular close.
AFTER_HOURS = {
    "SPY": (697.49, "https://www.coinglass.com/stocks/SPY"),
    "QQQ": (617.74, "https://finance.yahoo.com/quote/QQQ/?p=QQQ"),
    "QLD": (65.40, "https://www.webull.com.au/ticker/nysearca-qld"),
    "NVDA": (130.01, "https://finance.yahoo.com/quote/NVDA/?p=NVDA"),
    "IONQ": (21.595, "https://www.chartmill.com/stock/quote/IONQ/profile"),
}

# Deliberately preserve contrary quotes: public websites can conflict.
CONTRADICTORY_REGULAR = {
    "SPY": (690.87, "https://finabase.io/symbol/spy/history"),
    "QLD": (63.53, "https://finabase.io/symbol/qld/history"),
}
EXPECTED_ARTIFACT_SHA256 = (
    "df4e301e63e4a84f5b22b68db7ab74f3accb8687f4ac947e4400771a21838571")
ASOF = "2026-11-20"
ARCHIVED_LEFT = "44853890794"
ARCHIVED_RIGHT = "44871574162"
CLOSE_TOL_USD = 0.005  # half-cent for floating-point Parquet representation

def validate_quote_type(label):
    if label not in ("REGULAR_CLOSE", "AFTER_HOURS"):
        raise ValueError("SOURCE_QUOTE_TYPE_UNDEFINED")

def compare_frozen_quote(archived, benchmark, *, label, tol=CLOSE_TOL_USD):
    validate_quote_type(label)
    if archived is None or benchmark is None:
        raise ValueError("MISSING_PRICE")
    return abs(float(archived) - float(benchmark)) <= tol

def read_original_artifact(path):
    blob=Path(path).read_bytes()
    if sha256(blob).hexdigest()!=EXPECTED_ARTIFACT_SHA256:
        raise RuntimeError("HISTORIC_AUDIT_ARTIFACT_SHA256_MISMATCH")
    with ZipFile(BytesIO(blob)) as z:
        names=z.namelist()
        if names.count("first_vs_last_26asset.csv")!=1 or len(set(names))!=len(names):
            raise RuntimeError("HISTORICAL_PRICE_AUDIT_MISSING_OR_DUPLICATED")
        if z.testzip() is not None:
            raise RuntimeError("HISTORICAL_PRICE_AUDIT_CORRUPT")
        rows=list(csv.DictReader(StringIO(z.read("first_vs_last_26asset.csv").decode())))
    if len(rows)!=26 or len({row["symbol"] for row in rows})!=26:
        raise RuntimeError("HISTORIC_ASSET_COVERAGE_MISMATCH")
    if any(row["left_run"]!=ARCHIVED_LEFT or row["right_run"]!=ARCHIVED_RIGHT
           or row["last_shared"]!=ASOF for row in rows):
        raise RuntimeError("SOURCE_ARCHIVE_ID_OR_SESSION_MISMATCH")
    return {row["symbol"]:row for row in rows}

def audit(input_zip, output_dir):
    history=read_original_artifact(input_zip)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    results=[]
    for sym,(regular,sources) in REGULAR.items():
        if sym not in history or len(sources)<2:
            raise RuntimeError("MISSING_ASSET_OR_SOURCE:" +sym)
        row=history[sym]
        old=float(row["terminal_close_old"])
        final=float(row["terminal_close_new"])
        final_matches=compare_frozen_quote(final,regular,label="REGULAR_CLOSE")
        initial_matches=compare_frozen_quote(old,regular,label="REGULAR_CLOSE")
        ah=AFTER_HOURS.get(sym)
        initial_ah_match=(compare_frozen_quote(old,ah[0],label="AFTER_HOURS")
                          if ah else None)
        contradict=CONTRADICTORY_REGULAR.get(sym)
        discrepancy=(float(contradict[0]-regular) if contradict else None)
        results.append({
            "symbol":sym,"asof_session":ASOF,
            "archived_initial_run":ARCHIVED_LEFT,
            "archived_initial_close":old,
            "archived_final_run":ARCHIVED_RIGHT,
            "archived_final_close":final,
            "published_regular_close_consensus_usd":regular,
            "final_matches_published_close":final_matches,
            "initial_matches_published_close":initial_matches,
            "published_afterhours_usd":ah[0] if ah else None,
            "initial_matches_published_afterhours":initial_ah_match,
            "published_regular_source_urls":" | ".join(sources),
            "published_afterhours_source_url":ah[1] if ah else "",
            "contrary_published_regular_close":contradict[0] if contradict else None,
            "contrary_source_url":contradict[1] if contradict else "",
            "contrary_delta_from_consensus_usd":discrepancy,
            "status":("PUBLISHED_CONFLICT_REGULAR_MATCH" if contradict and final_matches
                      else "PUBLISHED_REGULAR_MATCH" if final_matches else
                      "REVISED_CLOSE_UNVERIFIED_HOLD")
        })
    def write_csv():
        p=out/"public_quoted_closes_vs_archived.csv"
        with p.open("w",newline="",encoding="utf8") as f:
            writer=csv.DictWriter(f,fieldnames=list(results[0]))
            writer.writeheader();writer.writerows(results)
    write_csv()
    report={
        "version":"daily20-web-published-close-check-20261121-v1",
        "asof_session":ASOF,
        "read_only":True,"production_writes":False,
        "live_execution":False,"strategy_promoted":False,
        "first_seal_retroactively_created":False,
        "source_retrieval": "2026-11-21 human-verified web search excerpts",
        "historical_archive_id":ARCHIVED_RIGHT,
        "input_artifact_sha256":EXPECTED_ARTIFACT_SHA256,
        "asset_count":len(results),
        "final_matches_2plus_public_published_regular_closes":
            sum(row["final_matches_published_close"] for row in results),
        "original_matches_public_afterhours_quotes":
            sum(row["initial_matches_published_afterhours"] is True for row in results),
        "published_afterhours_evidence_count":len(AFTER_HOURS),
        "initial_matches_regular_close_count":
            sum(row["initial_matches_published_close"] for row in results),
        "public_source_conflicts":list(CONTRADICTORY_REGULAR),
        "source_quality":{
            "number_of_distinct_sites_per_asset_min":2,
            "publication_snapshots_not_frozen_at_trade_time":True,
            "verified_as_nyse_nasdaq_consolidated_tape":False,
            "independent_underlying_vendor_lineage_verified":False,
            "time_of_exact_original_download_captured":False,
            "original_first_close_afterhours_contamination":"STRONG_HYPOTHESIS_NOT_CERTIFIED",
            "volume_not_consensus_verified":True,
        },
        "status":"SOURCE_FINALITY_ROOT_CAUSE_STRONGLY_INDICATED_RESEARCH_HOLD",
        "risk":"Do not use 2026-11-20 first-download daily closes as historical regular-session truth.",
        "next":"Obtain exchange-certified 16:00 print, initial 20:00 print and API download timestamps; prospectively test both on a new session.",
        "comparisons":results,
    }
    (out/"public_close_validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    if report["asset_count"]!=7 or report["final_matches_2plus_public_published_regular_closes"]!=7 or report["original_matches_public_afterhours_quotes"]!=5:
        raise RuntimeError("PUBLISHED_EXTERNAL_CLOSE_EVIDENCE_DISAGREEMENT")
    print("DAILY20_PUBLIC_CLOSE_EVIDENCE",json.dumps({
        "status":report["status"],
        "published_regular_close_matched":report["final_matches_2plus_public_published_regular_closes"],
        "first_afterhours_match":report["original_matches_public_afterhours_quotes"],
        "conflicting_public_regular_sources":report["public_source_conflicts"],
    }))
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    audit(a.archive,a.out)

if __name__=="__main__":
    main()
