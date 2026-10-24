#!/usr/bin/env python3
"""Read-only reconciliation of Feishu project flags and issued CSS invoices.

Writes only a derived QC tab. Project-level outstanding flags do not prove an
invoice remains unpaid. No payments are marked settled without bank evidence.
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

SHEET = os.getenv("SFDC_UNIFIED_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
TITLE = "Payment Reconciliation QC"
SOURCE_INVOICE = "Payment & Tax Invoice"
SOURCE_FEISHU = "Feishu Project Status"
BRIDGE = "Project ID Bridge Verified"
KST = dt.timezone(dt.timedelta(hours=9))

def norm(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

def mapping(rows):
    """Require explicit pair and VERIFIED status; never strip project prefixes."""
    pairs = {}
    conflicts = set()
    for row in rows[1:]:
        row = (row + [""] * 4)[:4]
        x_id, h_id, status, evidence = row
        x_id, h_id = norm(x_id), norm(h_id)
        if status.strip().upper() != "VERIFIED" or not evidence.strip():
            continue
        if not x_id.startswith("X") or not h_id.startswith("H"):
            continue
        if x_id in pairs and pairs[x_id] != h_id:
            conflicts.add(x_id)
        pairs[x_id] = h_id
    for x_id in conflicts:
        pairs.pop(x_id, None)
    return pairs, len(conflicts)

def analyze(invoices, feishu, bridge_rows):
    bridges, conflicts = mapping(bridge_rows)
    by_h = {}
    duplicates = set()
    for x_id, h_id in bridges.items():
        if h_id in by_h and by_h[h_id] != x_id:
            duplicates.add(h_id)
        by_h[h_id] = x_id
    for h_id in duplicates:
        by_h.pop(h_id, None)
    flag = {}
    for r in feishu[1:]:
        if r and norm(r[0]):
            flag[norm(r[0])] = r
    stats = Counter()
    invoice_ids = set()
    for r in invoices[1:]:
        if not r or not str(r[0]).strip():
            continue
        invoice = norm(r[0])
        if invoice in invoice_ids:
            stats["DUPLICATE_INVOICE_ID"] += 1
            continue
        invoice_ids.add(invoice)
        stats["INVOICES"] += 1
        # Column D = AMEA project; do not confuse AMEA ID with Feishu's X ID.
        # Canonical H project ID comes from the Quote Invoice Ledger, not here.
    stats["FEISHU_PROJECTS"] = len(flag)
    stats["OUTSTANDING_FLAG_PROJECTS"] = sum(len(r)>2 and str(r[2]).upper()=="YES" for r in flag.values())
    stats["ETAX_UNISSUED_FLAG_PROJECTS"] = sum(len(r)>1 and str(r[1]).upper()=="YES" for r in flag.values())
    stats["VERIFIED_X_TO_H_BRIDGES"] = len(by_h)
    stats["BRIDGE_CONFLICTS"] = conflicts + len(duplicates)
    return stats, by_h, flag

def request(session, method, path, **kw):
    import random
    import time
    for attempt in range(6):
        resp = session.request(method, "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET + path, timeout=45, **kw)
        if resp.status_code in (429,500,502,503,504) and attempt < 5:
            time.sleep(2**attempt + random.uniform(0,1))
            continue
        if not resp.ok:
            raise RuntimeError("SHEETS_HTTP_" + str(resp.status_code))
        return resp.json() if resp.content else {}

def value_range(session, title, cellrange):
    q = urllib.parse.quote("'" + title.replace("'", "''") + "'!" + cellrange, safe="")
    return request(session, "GET", "/values/" + q).get("values", [])

def main():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(creds)
    meta = request(session, "GET", "?fields=sheets.properties(title,sheetId)")
    titles = {s["properties"]["title"] for s in meta["sheets"]}
    if not {SOURCE_INVOICE, SOURCE_FEISHU, "Quote Invoice Ledger"}.issubset(titles):
        raise RuntimeError("REQUIRED_SOURCE_TABS_MISSING")
    invoices = value_range(session, SOURCE_INVOICE, "A1:P2000")
    projects = value_range(session, SOURCE_FEISHU, "A1:J2000")
    ledger = value_range(session, "Quote Invoice Ledger", "A1:P2000")
    bridge = value_range(session, BRIDGE, "A1:D2000") if BRIDGE in titles else []
    if not invoices or not projects or not ledger:
        raise RuntimeError("EMPTY_SOURCE_REFUSE_OVERWRITE")
    if invoices[0][0] != "Invoice Number" or projects[0][0] != "Project ID" or ledger[0][0] != "Invoice Number":
        raise RuntimeError("SOURCE_HEADER_CHANGED")
    stats, by_h, flags = analyze(invoices, projects, bridge)
    ledger_h = {norm(r[0]):norm(r[4]) for r in []}  # H is not in payment ledger; use Quote Invoice Ledger via project link only.
    # Feishu X is never equated to AMEA or CSS H without explicit mapping evidence.
    ledger_by_inv = {norm(r[0]):r for r in ledger[1:] if r and r[0]}
    validated_links = 0
    outstanding_linked = 0
    issued_linked = 0
    for row in invoices[1:]:
        if not row or not row[0]:
            continue
        key = norm(row[0])
        l = ledger_by_inv.get(key)
        if not l:
            continue
        # Quote Invoice Ledger does not store a verified H project key.
        # Do not claim a match from its AMEA or quote identifier.
        continue
    stats["INVOICE_TO_FEISHU_EXACT_VERIFIED"] = validated_links
    stats["LINKED_OUTSTANDING_FLAGS"] = outstanding_linked
    stats["LINKED_UNISSUED_FLAGS"] = issued_linked
    now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    out = [
        ["Payment Reconciliation QC", now, "READ_ONLY_SOURCE / DERIVED_OUTPUT"],
        ["Metric", "Value", "Meaning"],
        ["Invoice records", stats["INVOICES"], "Issued invoices, not receipts"],
        ["Feishu projects", stats["FEISHU_PROJECTS"], "Project-level status records"],
        ["Feishu outstanding flags", stats["OUTSTANDING_FLAG_PROJECTS"], "Not verified unpaid invoices"],
        ["Feishu eTAX unissued flags", stats["ETAX_UNISSUED_FLAG_PROJECTS"], "Not verified against CSS invoice number"],
        ["Verified X-to-H bridge pairs", stats["VERIFIED_X_TO_H_BRIDGES"], "Explicit bridge evidence only"],
        ["Bridge conflicts", stats["BRIDGE_CONFLICTS"], "Conflicting mappings excluded"],
        ["Invoice-to-Feishu verified links", stats["INVOICE_TO_FEISHU_EXACT_VERIFIED"], "Requires canonical invoice and project linkage; none inferred"],
        ["Invoice-level verified paid count", "UNKNOWN", "Remittance and receipt evidence absent"],
        ["Invoice-level verified collected KRW", "UNKNOWN", "Never interpret as zero"],
        ["Invoice-level verified outstanding KRW", "UNKNOWN", "Never sum project flags as unpaid balances"],
        ["Duplicate invoice keys", stats["DUPLICATE_INVOICE_ID"], "Investigate if nonzero"],
        ["Status", "REVIEW_REQUIRED", "Provide verified X↔H mapping AND invoice→H link plus remittance references"],
        ["Source tabs", SOURCE_INVOICE + "; " + SOURCE_FEISHU + "; Quote Invoice Ledger", "No operational source values modified"],
    ]
    if TITLE not in titles:
        request(session, "POST", ":batchUpdate", json={"requests":[{"addSheet":{"properties":{"title":TITLE,"gridProperties":{"rowCount":100,"columnCount":5,"frozenRowCount":2}}}}]})
    address = urllib.parse.quote("'" + TITLE + "'!A1:C" + str(len(out)), safe="")
    request(session, "PUT", "/values/" + address + "?valueInputOption=RAW", json={"values":out})
    print("PAYMENT_RECONCILIATION_QC_PASS invoices=%d projects=%d outstanding_flags=%d verified_invoice_links=%d" %
          (stats["INVOICES"], stats["FEISHU_PROJECTS"], stats["OUTSTANDING_FLAG_PROJECTS"], validated_links))
    if stats["DUPLICATE_INVOICE_ID"] or stats["BRIDGE_CONFLICTS"]:
        raise RuntimeError("QC_CONFLICT_REVIEW_REQUIRED")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PAYMENT_RECONCILIATION_QC_FAILED " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
