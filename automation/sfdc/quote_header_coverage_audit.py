#!/usr/bin/env python3
"""Exact-QID coverage between fresh Quotation process lines and old Quote Header.

Read-only evidence for a *recovery queue*, never a source conversion or quote
creation. A Quotation process row does not prove Quotation Name, SFDC record ID,
final Quote amount, or ownership. No identifiers or customer data are logged.
"""
from __future__ import annotations

from collections import defaultdict
import json
import os
import re
import sys
import urllib.parse

from quote_header_source_health import BOOK

QID = re.compile(r"^QID-\d{4}-\d{2}-\d{2}-[A-Za-z0-9-]+$", re.I)
RAW_TAB = "SFDC Email Quotation Raw"
HEADER_TAB = "SFDC Quote Export"
RAW_RANGE = ("A2:A4500", "G2:G4500", "J2:J4500")
HEADER_RANGE = ("H2:H2500", "E2:E2500", "B2:B2500")


def flag(value):
    v = str(value or "").strip().lower()
    return {"true": "1", "false": "0", "yes": "1", "no": "0",
            "active": "1", "inactive": "0", "1": "1", "0": "0"}.get(v, "")


def values_column(matrix):
    return [str(row[0]).strip() if row else "" for row in matrix]


def exact_qid_index(columns):
    if len(columns) != 3 or len({len(c) for c in columns}) != 1:
        raise ValueError("CROSSWALK_COLUMN_PARITY")
    groups = defaultdict(lambda: {"opps": set(), "active": set(), "rows": 0})
    invalid = 0
    for qid, opportunity, active in zip(*columns):
        if not qid and not opportunity and not active:
            continue
        qid = qid.strip().upper()
        if not QID.fullmatch(qid):
            invalid += 1
            continue
        entry = groups[qid]
        entry["rows"] += 1
        if opportunity:
            entry["opps"].add(opportunity.strip())
        entry["active"].add(flag(active))
    return groups, invalid


def compare(raw, old):
    fresh, raw_invalid = exact_qid_index(raw)
    historic, old_invalid = exact_qid_index(old)
    overlap = fresh.keys() & historic.keys()
    source_only = fresh.keys() - historic.keys()
    header_only = historic.keys() - fresh.keys()
    exact = active_only_conflict = opportunity_conflict = evidence_incomplete = 0
    for key in overlap:
        src, head = fresh[key], historic[key]
        if len(src["opps"]) != 1 or len(head["opps"]) != 1 or (
                len(src["active"]) != 1 or len(head["active"]) != 1 or
                "" in src["active"] or "" in head["active"]):
            evidence_incomplete += 1
        elif src["opps"] != head["opps"]:
            opportunity_conflict += 1
        elif src["active"] != head["active"]:
            active_only_conflict += 1
        else:
            exact += 1
    return {
        "status": "REVIEW_QUEUE" if source_only or header_only or
                  active_only_conflict or opportunity_conflict or evidence_incomplete or
                  raw_invalid or old_invalid else "QID_PARITY_ONLY",
        "process_qids": len(fresh), "header_qids": len(historic),
        "overlap_qids": len(overlap), "process_only_qids": len(source_only),
        "header_only_qids": len(header_only),
        "exact_qid_opportunity_active": exact,
        "active_mismatch": active_only_conflict,
        "opportunity_mismatch": opportunity_conflict,
        "ambiguous_or_missing_evidence": evidence_incomplete,
        "invalid_process_rows": raw_invalid, "invalid_header_rows": old_invalid,
        "source_process_report_certifies_quote_header": False,
        "quote_name_verified": False,
        "quote_price_verified": False,
        "quote_sfdc_record_id_verified_for_new_only": False,
        "sfdc_writes": 0, "feishu_writes": 0,
    }


def read_source():
    data = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "")
    if not data:
        raise RuntimeError("SOURCE_CREDENTIAL_UNAVAILABLE")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    client = AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(data), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]))
    def get(tab, range_a1):
        segment = urllib.parse.quote("'" + tab.replace("'", "''") +
                                     "'!" + range_a1, safe="")
        url = "https://sheets.googleapis.com/v4/spreadsheets/" + BOOK + "/values/" + segment
        response = client.get(url, timeout=35)
        if not response.ok:
            raise RuntimeError("CROSSWALK_SOURCE_READ_FAILED")
        return values_column(response.json().get("values", []))
    return [[get(RAW_TAB, r) for r in RAW_RANGE],
            [get(HEADER_TAB, r) for r in HEADER_RANGE]]


def main():
    try:
        raw, old = read_source()
        result = compare(raw, old)
    except Exception as error:
        result = {"status": "SOURCE_UNAVAILABLE",
                  "error_type": type(error).__name__,
                  "source_process_report_certifies_quote_header": False,
                  "quote_name_verified": False, "quote_price_verified": False,
                  "sfdc_writes": 0, "feishu_writes": 0}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write("### Quotation process ↔ Quote Header exact QID parity\n")
            file.write("Status **" + result["status"] + "**. ")
            file.write("Source-only and header-only counts require review, never auto-promotion.\n")
            for k in ("process_qids", "header_qids", "overlap_qids",
                      "process_only_qids", "header_only_qids",
                      "exact_qid_opportunity_active", "active_mismatch"):
                if k in result:
                    file.write("- " + k + ": " + str(result[k]) + "\n")
    if result["status"] == "SOURCE_UNAVAILABLE":
        sys.exit(2)


if __name__ == "__main__":
    main()
