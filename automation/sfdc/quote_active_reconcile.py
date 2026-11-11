#!/usr/bin/env python3
"""Read-only SFDC Quote approval/active reconciliation from CSV exports.

Usage:
 python3 automation/sfdc/quote_active_reconcile.py --approvals approvals.csv --quotes quotes.csv --output quote_validation.csv
No Salesforce writes. No email sends. Unknown Active is never treated as valid.
"""
import argparse
import csv
import pathlib
import sys

TRUE = {"true", "1", "yes", "active"}
FALSE = {"false", "0", "no", "inactive"}

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader)

def first(row, *names):
    for name in names:
        value = (row.get(name) or "").strip()
        if value:
            return value
    return ""

def active_flag(value):
    norm = value.strip().lower()
    if norm in TRUE:
        return True
    if norm in FALSE:
        return False
    return None

def reconcile(approvals, quotes):
    lookup = {}
    duplicate = set()
    for row in quotes:
        qid = first(row, "Quote Record ID", "Id", "SFDC Quote ID")
        if not qid:
            continue
        if qid in lookup:
            duplicate.add(qid)
        lookup[qid] = row
    output = []
    for approval in approvals:
        qid = first(approval, "salesforce_record_id", "sfdc_quote_id")
        amea = first(approval, "quotation_id", "amea_quote_id")
        evidence = first(approval, "approval_evidence")
        row = lookup.get(qid, {})
        active = active_flag(first(row, "Is Active", "IsActive", "Active"))
        status = first(row, "Status", "Approval Status")
        currency = first(row, "CurrencyIsoCode", "Quote Currency", "Currency")
        amount = first(row, "GrandTotal", "Total Amount", "Quote Total Amount")
        approved = evidence in {"APPROVED_TEXT", "VERIFIED_LEGACY_RECORD"} or status.lower() == "approved"
        if not qid or qid in duplicate:
            validation = "AMBIGUOUS_OR_MISSING_QUOTE_ID"
        elif not row:
            validation = "QUOTE_OBJECT_NOT_FOUND"
        elif active is None:
            validation = "ACTIVE_UNKNOWN"
        elif active is False:
            validation = "INACTIVE"
        elif not approved:
            validation = "APPROVAL_UNKNOWN"
        elif not currency or not amount:
            validation = "FINANCIAL_FIELDS_MISSING"
        else:
            validation = "APPROVED_ACTIVE_VERIFIED"
        output.append({
            "amea_quote_id": amea,
            "sfdc_quote_id": qid,
            "approved_evidence": evidence,
            "active_status": "UNKNOWN" if active is None else str(active).upper(),
            "currency": currency,
            "source_amount": amount,
            "eligible_amount": amount if validation == "APPROVED_ACTIVE_VERIFIED" else "",
            "validation_status": validation,
        })
    return output

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--approvals", required=True)
    p.add_argument("--quotes", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    a_fields, approvals = read_csv(args.approvals)
    q_fields, quotes = read_csv(args.quotes)
    if "salesforce_record_id" not in a_fields and "sfdc_quote_id" not in a_fields:
        p.error("approval export missing stable SFDC quote id")
    if not any(k in q_fields for k in ("Quote Record ID", "Id", "SFDC Quote ID")):
        p.error("Quote object export missing stable quote id")
    result = reconcile(approvals, quotes)
    target = pathlib.Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["amea_quote_id","sfdc_quote_id","approved_evidence","active_status","currency","source_amount","eligible_amount","validation_status"])
        writer.writeheader()
        writer.writerows(result)
    counts = {}
    for row in result:
        key = row["validation_status"]
        counts[key] = counts.get(key, 0) + 1
    print("QUOTE_RECONCILIATION", counts)
    return 0

if __name__ == "__main__":
    sys.exit(main())
