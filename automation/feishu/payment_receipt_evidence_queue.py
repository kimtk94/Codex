#!/usr/bin/env python3
"""Generated Receipt-to-Invoice evidence queue; NEVER certifies a paid invoice.

Inputs are read-only generated Sheets snapshots. Outputs go solely to the
derived Payment Receipt Evidence Review tab. Any cash/owner attribution
requires independent primary evidence, not a plausible source-table match.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from collections import Counter

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from payment_reconciliation_qc import (
    SHEET, RECEIPT_HEADERS, RECEIPT_GROUPS, RECEIPT_NUMBER,
    amount_int, request, value_range,
)

TAB = "Payment Receipt Evidence Review"
HEAD = [
    "Invoice Number", "AMEA Project", "Issued Date", "Invoice Gross KRW",
    "Receipt Date", "Receipt Amount KRW", "Receipt Source Row",
    "Receipt Source Section", "Receipt References", "Evidence Class",
    "Receipt Snapshot Date", "Exact Outstanding Reference",
    "Owner Scope", "Verified Paid KRW", "Required Next Check",
]
SECTIONS = {3: "A-D", 6: "F-H", 12: "J-M"}
EPOCH = dt.date(1899, 12, 30)

def parse_day(value):
    value = str(value or "").strip()
    if not value:
        return None
    if re.fullmatch(r"\d{5}(?:\.0+)?", value):
        serial = int(value.split(".")[0])
        return EPOCH + dt.timedelta(days=serial) if 40000 <= serial <= 60000 else None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S",
                "%d-%b-%y", "%d-%B-%y", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None

def source_snapshot(manifest, receipts):
    if not manifest or manifest[0][:3] != [
        "Source", "Source Date", "Synced At KST"
    ]:
        raise RuntimeError("FEISHU_MANIFEST_HEADER_CHANGED")
    rows = [r for r in manifest[1:] if r and r[0] == "Payment Receipt"]
    if len(rows) != 1 or len(rows[0]) < 6:
        raise RuntimeError("RECEIPT_MANIFEST_IDENTITY_MISSING")
    row = rows[0]
    parsed = parse_day(row[1])
    if parsed is None or str(row[5]) != "HEADER_MATCHED":
        raise RuntimeError("RECEIPT_MANIFEST_DATE_OR_SCHEMA_UNVERIFIED")
    if int(row[4]) != len(receipts)-1:
        raise RuntimeError("RECEIPT_MANIFEST_ROW_PARITY_FAILED")
    return parsed

def build(invoices, receipts, outstanding, manifest):
    if not invoices or invoices[0][:7] != [
        "Invoice Number", "Quotation ID", "SFDC Quote ID",
        "AMEA Project ID", "Institution", "Invoice Date",
        "Invoice Amount (KRW)"
    ]:
        raise RuntimeError("ISSUED_INVOICE_SOURCE_HEADER_CHANGED")
    if not receipts or len(receipts[0]) < 13 or any(
        str(receipts[0][i]) != label for i,label in RECEIPT_HEADERS
    ):
        raise RuntimeError("RECEIPT_SOURCE_HEADER_CHANGED")
    if not outstanding or outstanding[0][6] != "CMS Invoice Number":
        raise RuntimeError("OUTSTANDING_CMS_SOURCE_HEADER_CHANGED")
    snapshot = source_snapshot(manifest, receipts)
    exact_outstanding = set()
    for line in outstanding[1:]:
        if len(line) > 6:
            exact_outstanding.update(RECEIPT_NUMBER.findall(str(line[6]).upper()))

    # One section may list multiple CMS invoice numbers: never allocate its
    # total receipt amount to one invoice, even when it matches numerically.
    references = {}
    for index,line in enumerate(receipts[1:],start=2):
        for date_col,amount_col,cms_col in RECEIPT_GROUPS:
            raw = str(line[cms_col] or "") if len(line) > cms_col else ""
            numbers = RECEIPT_NUMBER.findall(raw.upper())
            if not numbers:
                continue
            amount = amount_int(line[amount_col]) if len(line)>amount_col else None
            day = parse_day(line[date_col]) if len(line)>date_col else None
            for number in set(numbers):
                references.setdefault(number, []).append({
                    "date":day, "amount":amount, "row":index,
                    "section":SECTIONS[cms_col], "count":len(numbers),
                    "exact":raw.strip()==number,
                })

    output = [HEAD]
    categories = Counter()
    seen = set()
    for row in invoices[1:]:
        if not row or not str(row[0]).strip():
            continue
        number = str(row[0]).strip()
        if not re.fullmatch(r"2091(?:25|26)\d{6}", number):
            raise RuntimeError("INVOICE_ID_FORMAT_CHANGED")
        if number in seen:
            raise RuntimeError("DUPLICATE_ISSUED_INVOICE")
        seen.add(number)
        issue = parse_day(row[5]) if len(row)>5 else None
        gross = amount_int(row[6]) if len(row)>6 else None
        refs = references.get(number, [])
        receipt = refs[0] if len(refs)==1 else {}
        flag = "YES" if number in exact_outstanding else "NO_EXACT_CMS"
        if not refs:
            code,check = "NO_RECEIPT_REFERENCE","Find matching CMS number in a newer original Receipt"
        elif len(refs)!=1:
            code,check = "DUPLICATE_REFERENCE_REVIEW","Review multiple Receipt sections/rows; do not double-count"
        elif receipt["count"]!=1:
            code,check = "GROUPED_ALLOCATION_REVIEW","Require per-invoice allocation for grouped CMS receipt"
        elif gross is None or receipt["amount"] is None:
            code,check = "RECEIPT_AMOUNT_MISSING_REVIEW","Obtain original invoice and receipt amounts"
        elif receipt["amount"]!=gross:
            code,check = "RECEIPT_AMOUNT_MISMATCH_REVIEW","Review partial, excess, or unrelated remittance"
        elif not receipt["exact"]:
            code,check = "RECEIPT_CMS_SUFFIX_REVIEW","Verify full CMS number and suffix against original"
        elif issue is None or receipt["date"] is None:
            code,check = "RECEIPT_DATE_MISSING_REVIEW","Verify original date and issue chronology"
        elif receipt["date"] < issue:
            code,check = "RECEIPT_BEFORE_ISSUANCE_REVIEW","Verify receipt predates invoice/advance payment"
        elif receipt["date"] > snapshot:
            code,check = "RECEIPT_AFTER_SNAPSHOT_REVIEW","Verify source version and date conflict"
        elif number in exact_outstanding:
            code,check = "RECEIPT_OUTSTANDING_CONFLICT_REVIEW","Resolve dated outstanding and receipt conflict"
        else:
            code,check = "EXACT_AMOUNT_DATE_RECEIPT_CANDIDATE","Confirm primary remittance and salesperson ownership"
        categories[code] += 1
        output.append([
            number, str(row[3]) if len(row)>3 else "",
            issue.isoformat() if issue else "", gross if gross is not None else "",
            receipt["date"].isoformat() if receipt.get("date") else "",
            receipt.get("amount") if receipt.get("amount") is not None else "",
            receipt.get("row",""), receipt.get("section",""), len(refs), code,
            snapshot.isoformat(), flag, "OWNER_NOT_VERIFIED", "UNKNOWN", check,
        ])
    if len(output)<2 or sum(categories.values())!=len(seen):
        raise RuntimeError("RECEIPT_REVIEW_ACCOUNTING_FAILED")
    return output, categories

def assert_existing_qc(qc, rows, classes):
    facts = {str(row[0]):str(row[1]) for row in qc if len(row)>1}
    total = len(rows)-1
    linked = total-classes["NO_RECEIPT_REFERENCE"]
    audit = {
        "Invoice records":total,
        "Receipt linked invoice IDs":linked,
        "Receipt single-ID exact-amount candidates":classes["EXACT_AMOUNT_DATE_RECEIPT_CANDIDATE"],
        "Receipt grouped-allocation review":classes["GROUPED_ALLOCATION_REVIEW"],
        "Receipt duplicate-ID review":classes["DUPLICATE_REFERENCE_REVIEW"],
        "Receipt amount mismatch review":classes["RECEIPT_AMOUNT_MISMATCH_REVIEW"],
    }
    for key,value in audit.items():
        if str(value)!=facts.get(key):
            raise RuntimeError("EXISTING_RECEIPT_QC_PARITY_FAILED_"+key.replace(" ","_"))
    if facts.get("Invoice-level verified paid count") != "UNKNOWN":
        raise RuntimeError("PAID_STATUS_NOT_PROVEN")
    return audit

def main():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(creds)
    meta = request(session,"GET","?fields=sheets.properties(title,sheetId)")
    titles = {x["properties"]["title"] for x in meta.get("sheets",[])}
    source_tabs = {
        "Payment & Tax Invoice", "Feishu Latest Receipts",
        "Feishu Latest Outstanding", "Feishu Source Manifest",
        "Payment Reconciliation QC",
    }
    if not source_tabs.issubset(titles):
        raise RuntimeError("RECEIPT_SOURCE_TABS_MISSING")
    invoices=value_range(session,"Payment & Tax Invoice","A1:G2000")
    receipts=value_range(session,"Feishu Latest Receipts","A1:M2000")
    outstanding=value_range(session,"Feishu Latest Outstanding","A1:G2000")
    manifest=value_range(session,"Feishu Source Manifest","A1:G30")
    qc=value_range(session,"Payment Reconciliation QC","A1:C50")
    rows,classes=build(invoices,receipts,outstanding,manifest)
    assert_existing_qc(qc,rows,classes)
    prior=value_range(session,TAB,"A1:O2000") if TAB in titles else []
    if prior and (prior[0]!=HEAD or len(prior)>len(rows)):
        raise RuntimeError("RECEIPT_QUEUE_HEADER_OR_SHRINK_REVIEW")
    if TAB not in titles:
        request(session,"POST",":batchUpdate",json={"requests":[{
            "addSheet":{"properties":{"title":TAB,
                "gridProperties":{"rowCount":2000,"columnCount":15,"frozenRowCount":1}}}}]})
    address=urllib.parse.quote("'"+TAB+"'!A1:O"+str(len(rows)),safe="")
    request(session,"PUT","/values/"+address+"?valueInputOption=RAW",json={"values":rows})
    observed=value_range(session,TAB,"A1:O"+str(len(rows)))
    if len(observed)!=len(rows) or observed[0]!=HEAD:
        raise RuntimeError("RECEIPT_QUEUE_READBACK_HEADER_OR_ROWS_FAILED")
    if [str(r[0]) for r in observed[1:]]!=[str(r[0]) for r in rows[1:]]:
        raise RuntimeError("RECEIPT_QUEUE_READBACK_IDENTITIES_FAILED")
    if Counter(r[9] for r in observed[1:])!=classes:
        raise RuntimeError("RECEIPT_QUEUE_READBACK_CLASS_PARITY_FAILED")
    print("PAYMENT_RECEIPT_QUEUE_PASS invoices=%s linked=%s exact_candidate=%s grouped=%s duplicate=%s mismatch=%s no_reference=%s owner=UNVERIFIED paid=UNKNOWN snapshot=%s" %
          (len(rows)-1,len(rows)-1-classes["NO_RECEIPT_REFERENCE"],
           classes["EXACT_AMOUNT_DATE_RECEIPT_CANDIDATE"],
           classes["GROUPED_ALLOCATION_REVIEW"],classes["DUPLICATE_REFERENCE_REVIEW"],
           classes["RECEIPT_AMOUNT_MISMATCH_REVIEW"],classes["NO_RECEIPT_REFERENCE"],
           rows[1][10]),flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PAYMENT_RECEIPT_QUEUE_FAILED "+type(exc).__name__,file=sys.stderr)
        raise
