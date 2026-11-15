#!/usr/bin/env python3
"""Learn common SFDC Opportunity/Quotation patterns from authenticated QQ Report snapshots.

Read only. Never exports customer rows, names, prices, CRM IDs or individual
quotations to GitHub logs/artifacts. Produces aggregated process templates only.
The output is a reference for NO-SAVE drafts, never approval to auto-create.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from statistics import median
from urllib.parse import quote

SHEET_ID = os.environ.get("SFDC_PATTERN_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
OPP_TAB = "SFDC Email Opportunities Raw"
QUOTE_TAB = "SFDC Email Quotation Raw"
AUDIT_TAB = "SFDC Email Ingest Audit"
QQ_STATES = {"STAGED_NOT_PROMOTED", "PRESERVED_NO_NEW_REPORT"}
EXPECTED_QUOTE = {"SFDC Quotation ID", "Quotation Product ID", "Opportunity ID", "Active",
                  "Quotation Process Name", "Quote Process Name", "*Account Id", "Data Unit"}
EXPECTED_OPP = {"Opportunity ID", "Account ID", "Opportunity Owner", "Stage", "Opportunity Name"}
EXPECTED_AUDIT = {"Entity", "Source Received KST", "Ingest Checked KST", "Rows", "Unique IDs",
                  "Missing IDs", "Content SHA256", "State", "Source Kind"}
QID_RX = re.compile(r"^QID-[\d-]{8,50}$")
OPP_RX = re.compile(r"^Opp-[\d-]{8,50}$")


def normalize_matrix(matrix, expected):
    if not matrix:
        raise ValueError("EMPTY_SOURCE")
    head = matrix[0]
    if len(head) != len(set(head)) or not expected.issubset(set(head)):
        raise ValueError("UNEXPECTED_REPORT_SCHEMA")
    rows = [r + [""] * (len(head) - len(r)) for r in matrix[1:] if any(str(v).strip() for v in r)]
    records = [dict(zip(head, r)) for r in rows]
    return head, rows, records


def verify_mail_audit(matrices, audit_records):
    """Mirror the QQ report ingestion content-hash gate, independently per entity."""
    evidence = {}
    for entity, key in (("Opportunities", "opportunities"), ("Quotation", "quotation")):
        matching = [r for r in audit_records if r.get("Entity") == entity]
        if len(matching) != 1:
            raise ValueError("SOURCE_AUDIT_NOT_UNIQUE")
        row = matching[0]
        if row.get("State") not in QQ_STATES or row.get("Source Kind") != "QQ IMAP":
            raise ValueError("SOURCE_AUDIT_NOT_TRUSTED")
        head, data, records = matrices[key]
        digest = hashlib.sha256(json.dumps([head, data], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        if digest != row.get("Content SHA256"):
            raise ValueError("SOURCE_SHA256_MISMATCH")
        if len(records) != int(row.get("Rows") or "-1"):
            raise ValueError("SOURCE_AUDIT_ROW_MISMATCH")
        if int(row.get("Missing IDs") or "-1") != 0:
            raise ValueError("SOURCE_IDS_MISSING")
        distinct_col = "Opportunity ID" if entity == "Opportunities" else "SFDC Quotation ID"
        if len({r.get(distinct_col, "") for r in records}) != int(row.get("Unique IDs") or "-1"):
            raise ValueError("SOURCE_UNIQUE_ID_MISMATCH")
        evidence[key] = {"received_kst": row.get("Source Received KST", ""),
                         "checked_kst": row.get("Ingest Checked KST", ""),
                         "state": row["State"], "hash_verified": True}
    return evidence


def build_report(opps, lines, min_support=10, min_share=0.01, evidence=None):
    """Analyze ALL rows, but promote only recurring single-product templates."""
    opportunity_map = {}
    for r in opps:
        oid = str(r.get("Opportunity ID", "")).strip()
        if OPP_RX.fullmatch(oid):
            if oid in opportunity_map:
                raise ValueError("DUPLICATED_OPPORTUNITY_ID")
            opportunity_map[oid] = r

    quotes = defaultdict(list)
    for r in lines:
        qid = str(r.get("SFDC Quotation ID", "")).strip()
        if not QID_RX.fullmatch(qid):
            raise ValueError("QUOTE_ID_INVALID")
        quotes[qid].append(r)

    eligible_signatures = Counter()
    process_rows = Counter()
    all_quote_products = 0
    product_distribution = Counter()
    reasons = Counter()
    matched_opp_ids = set()
    multiple_opp_qids = Counter()
    total_active = 0
    mode_distribution = Counter()
    samples = []
    for qid, rows in quotes.items():
        def uniq(col):
            return {str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()}
        product_ids = uniq("Quotation Product ID")
        opp_ids = uniq("Opportunity ID")
        active = uniq("Active")
        product_distribution[len(product_ids)] += 1
        all_quote_products += len(product_ids)
        if active == {"1"}:
            total_active += 1
        if len(opp_ids) == 1 and next(iter(opp_ids)) in opportunity_map:
            matched_opp_ids.add(next(iter(opp_ids)))
            multiple_opp_qids[next(iter(opp_ids))] += 1
        # All reasons reported without individual records; one primary reason per Quote.
        if len(opp_ids) != 1:
            reasons["MISSING_OR_CONFLICTING_OPPORTUNITY_ID"] += 1
            continue
        opp_id = next(iter(opp_ids))
        opp = opportunity_map.get(opp_id)
        if opp is None:
            reasons["OPPORTUNITY_OUTSIDE_REPORT_SCOPE"] += 1
            continue
        if active != {"1"}:
            reasons["INACTIVE_OR_CONFLICTING_ACTIVE"] += 1
            continue
        if len(product_ids) != 1:
            reasons["MULTI_PRODUCT_MANUAL_REVIEW"] += 1
            continue
        # Salesforce 001 IDs may be 15 or 18 characters; never join on names.
        accounts = {str(r.get("*Account Id", "")).strip()[:15] for r in rows if r.get("*Account Id")}
        opp_account = str(opp.get("Account ID", "")).strip()[:15]
        if len(accounts) != 1 or not opp_account or next(iter(accounts)) != opp_account:
            reasons["ACCOUNT_RELATION_UNVERIFIED"] += 1
            continue
        templates = uniq("Quotation Process Name")
        if len(templates) != 1:
            reasons["PRODUCT_TEMPLATE_INCONSISTENT"] += 1
            continue
        template = next(iter(templates))
        ordered = tuple(p.strip() for p in template.split(",") if p.strip())
        observed = [str(r.get("Quote Process Name", "")).strip() for r in rows]
        if not (3 <= len(ordered) <= 12) or Counter(observed) != Counter(ordered):
            reasons["PROCESS_TEMPLATE_INCONSISTENT"] += 1
            continue
        # Signature ignores source display order for recurrence; preserved order
        # is never used to auto-populate process quantity or unit price.
        signature = tuple(sorted(ordered))
        eligible_signatures[signature] += 1
        for p in observed:
            process_rows[p] += 1
        for r in rows:
            if r.get("Quote Process Name") in {"Sequencing by data amount", "Sequencing by lane", "Sequencing by sample"}:
                mode_distribution[r["Quote Process Name"]] += 1
                if r.get("Data Unit") in {"G raw data", "G", "Gb"}:
                    val = str(r.get("Data Size", "")).strip().replace(",", "")
                    try:
                        n = float(val)
                        if 0 < n <= 10000:
                            samples.append(n)
                    except (ValueError, TypeError):
                        pass
    eligible = sum(eligible_signatures.values())
    common = []
    for signature, n in eligible_signatures.most_common():
        if n < min_support or (eligible and n / eligible < min_share):
            continue
        common.append({"processes": list(signature), "quotes": n,
                       "share_of_eligible_pct": round(n / eligible * 100, 1)})
    promoted = sum(t["quotes"] for t in common)
    return {
        "status": "PASS" if eligible else "BLOCK_NO_ELIGIBLE_TEMPLATES",
        "purpose": "READ_ONLY_POPULAR_PATTERNS_FOR_NO_SAVE_DRAFTS",
        "source": {"opportunities": len(opps), "unique_opportunities": len(opportunity_map),
                   "quote_process_rows": len(lines), "unique_quotes": len(quotes),
                   "quote_products": all_quote_products, "evidence": evidence or {}},
        "coverage": {"one_product_quotes": product_distribution[1], "multi_product_quotes": sum(n for k, n in product_distribution.items() if k > 1),
                     "active_quotes": total_active, "matched_opportunity_ids": len(matched_opp_ids),
                     "opportunities_without_quote": len(set(opportunity_map) - matched_opp_ids),
                     "opportunities_with_multiple_quotes": sum(v > 1 for v in multiple_opp_qids.values()),
                     "eligible_quotes": eligible, "popular_template_quotes": promoted,
                     "unpromoted_quotes": len(quotes) - promoted,
                     "exclude_reasons": dict(sorted(reasons.items()))},
        "patterns": common,
        "process_row_counts_eligible": dict(process_rows.most_common()),
        "sequencing_modes_eligible": dict(mode_distribution.most_common()),
        "sequencing_gb_observed_median_not_default": median(samples) if samples else None,
        "policy": {"crm_writes": 0, "customer_rows_exported": 0,
                   "price_defaulting": False, "quantity_defaulting": False,
                   "contact_requires_live_003_001_recheck": True,
                   "manual_review_for_multi_product": True,
                   "opportunity_and_quote_same_base_name_for_new_draft": True,
                   "description_must_be_newly_authored": True}
    }


def read_live_matrix(session, tab, cells):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(chr(39) + tab + chr(39) + '!' + cells, safe='')}"
    response = session.get(url, timeout=50)
    if not response.ok:
        raise ValueError("SHEETS_READ_BLOCKED")
    return response.json().get("values", [])


def run_live():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise ValueError("READ_ONLY_CREDENTIAL_MISSING")
    cred = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session = AuthorizedSession(cred)
    matrices = {
        "opportunities": normalize_matrix(read_live_matrix(session, OPP_TAB, "A1:O2000"), EXPECTED_OPP),
        "quotation": normalize_matrix(read_live_matrix(session, QUOTE_TAB, "A1:Y6000"), EXPECTED_QUOTE),
    }
    _, _, audits = normalize_matrix(read_live_matrix(session, AUDIT_TAB, "A1:J30"), EXPECTED_AUDIT)
    evidence = verify_mail_audit(matrices, audits)
    return build_report(matrices["opportunities"][2], matrices["quotation"][2], evidence=evidence)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None, help="Write aggregated, non-PII summary only")
    parser.add_argument("--quiet", action="store_true", help="Do not log aggregate business metrics")
    args = parser.parse_args()
    try:
        result = run_live()
    except Exception as exc:
        # Do not disclose potentially sensitive response bodies/errors in public logs.
        print(json.dumps({"status": "BLOCK", "reason": str(exc) if isinstance(exc, ValueError) else "SOURCE_ACCESS_FAILED", "crm_writes": 0}))
        raise SystemExit(2)
    data = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data + "\n", encoding="utf-8")
    if not args.quiet:
        print(data)


if __name__ == "__main__":
    main()