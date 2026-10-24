#!/usr/bin/env python3
"""Idempotently mirror validated 2025 QQ invoices to a dedicated BI ledger.
No email mutations, no changes to existing 2025 official revenue or 2026 invoices.
"""
import json
import os
import re
import urllib.parse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SOURCE = os.getenv("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
DEST = os.getenv("BI_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
SOURCE_TAB = "QQ Historical Invoice Backfill"
DEST_TAB = "BI 2025 QQ Verified Invoice"
HEAD = ["Invoice Number", "Invoice Month", "Invoice KRW", "Invoice K USD",
        "AMEA ID", "H Project ID", "Evidence", "Reconciliation",
        "QQ Source UID", "Synced Snapshot"]

def path(tab, area):
    return urllib.parse.quote("'" + tab + "'!" + area, safe="")

def read(session, book, tab, area):
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + book + "/values/" + path(tab, area)
    response = session.get(url, timeout=65)
    response.raise_for_status()
    return response.json().get("values", [])

def put(session, book, tab, area, values):
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + book + "/values/" + path(tab, area)
    response = session.put(url, params={"valueInputOption": "USER_ENTERED"},
                           json={"values": values}, timeout=65)
    response.raise_for_status()

def normalize(source_rows):
    result = {}
    for row in source_rows[1:]:
        if not row or not row[0]:
            continue
        row += [""] * max(0, 11-len(row))
        invoice, month, amount, amea, h_id = row[:5]
        if not re.fullmatch(r"209125[0-9]{6}", invoice):
            raise ValueError("Unexpected non-2025 invoice")
        if not re.fullmatch(r"2025-(0[1-9]|1[0-2])", month):
            raise ValueError("Unknown 2025 invoice month")
        value = int(amount)
        if value <= 0:
            raise ValueError("Invalid invoice amount")
        evidence = row[9]
        if evidence not in ("CSS_TAX_INVOICE_LIST_VERIFIED_LEGACY",
                            "FILENAME_PARSED", "SUBJECT_CORROBORATED_FILENAME"):
            raise ValueError("Invoice provenance is not verified")
        if invoice in result and result[invoice][2] != value:
            raise ValueError("Conflicting amount for invoice")
        result[invoice] = [invoice, month, value, "=CROW/1500000",
                           amea, h_id, evidence, "VERIFIED_QQ_HISTORICAL",
                           row[6] + ":" + row[7], "2025 QQ sync"]
    return result

def main():
    info = json.loads(os.environ["CKD_DRIVE_SA_JSON"])
    auth = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(auth)
    origin = read(session, SOURCE, SOURCE_TAB, "A1:K10000")
    if not origin or origin[0][:3] != ["invoice_number", "issued_month", "amount_krw"]:
        raise ValueError("Unexpected source schema")
    records = normalize(origin)
    target = read(session, DEST, DEST_TAB, "A1:J2000")
    if not target or target[0] != HEAD:
        raise ValueError("Unexpected target schema")
    previous = {row[0]: row for row in target[1:] if row and row[0]}
    if len(previous) != len(target[1:]):
        raise ValueError("Duplicate or empty invoice row in BI target")
    for invoice, row in previous.items():
        if invoice not in records:
            raise ValueError("Previously verified invoice vanished from source")
        if int(row[2]) != records[invoice][2]:
            raise ValueError("Amount conflict in BI target")
    if len(records) > 1900:
        raise ValueError("Target sheet would exceed safe bounds")
    combined = []
    for n, invoice in enumerate(sorted(records, reverse=True), start=2):
        rec = list(records[invoice])
        rec[3] = "=C" + str(n) + "/1500000"
        combined.append(rec)
    if len(records) == len(previous):
        print("QQ_2025_BI_SYNC_PASS unchanged=" + str(len(records)))
        return
    put(session, DEST, DEST_TAB, "A2", combined)
    print("QQ_2025_BI_SYNC_PASS imported=" + str(len(combined))
          + " added=" + str(len(records)-len(previous))
          + " amount_krw=" + str(sum(r[2] for r in combined)))
if __name__ == "__main__":
    main()
