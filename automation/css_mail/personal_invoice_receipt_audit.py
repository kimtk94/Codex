#!/usr/bin/env python3
"""Read-only, per-invoice October receipt audit; never equates receipt to sales ownership."""
import json
import os
import sys
import urllib.parse
from collections import Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from invoice_ownership import classify_invoice

SHEET = os.getenv("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
MONTH = os.getenv("INVOICE_AUDIT_MONTH", "2026-10")
USER_EMAIL = os.getenv("INVOICE_AUDIT_USER_EMAIL", "taehoon.kim@novogene.com").strip().lower()

def fetch(session, path):
    result = session.get("https://sheets.googleapis.com/v4/spreadsheets/" + SHEET + path, timeout=80)
    result.raise_for_status()
    return result.json()

def get_rows(session, tab, area):
    q = urllib.parse.quote("'" + tab + "'!" + area, safe="")
    return fetch(session, "/values/" + q).get("values", [])

def audit(session):
    records = get_rows(session, "CSS Tax Invoice List", "A1:N2000")
    if not records or records[0][:4] != ["invoice_month", "issued_at", "invoice_number", "amount_krw"]:
        raise RuntimeError("INVOICE_HEADER_MISMATCH")
    invoices = [dict(zip(records[0], row)) for row in records[1:] if row and row[0] == MONTH]
    if not invoices:
        raise RuntimeError("NO_INVOICES_FOR_MONTH")
    # Every source_row is the *Google Sheet row number*, not the IMAP UID.
    source_rows = set()
    for inv in invoices:
        source = str(inv.get("source_row", "")).strip()
        if source.isdigit() and int(source) > 1:
            source_rows.add(int(source))
    # BatchGet only evidence rows referenced by the canonical invoice ledger.
    ranges = ["'All Emails'!D%d:J%d" % (r,r) for r in sorted(source_rows)]
    evidence = {}
    for start in range(0,len(ranges),90):
        query = urllib.parse.urlencode([("ranges",r) for r in ranges[start:start+90]])
        raw = fetch(session, "/values:batchGet?" + query).get("valueRanges",[])
        for item in raw:
            address = item.get("range","")
            import re
            m = re.search(r"![A-Z]+(\d+):",address)
            if m:
                evidence[int(m.group(1))] = (item.get("values") or [[]])[0]
    out = []
    for inv in invoices:
        row = inv.get("source_row","")
        values = evidence.get(int(row),[]) if str(row).isdigit() else []
        # D:J => D sender name, E from_email, F to, G cc, H bcc, I subject, J attachment
        sender = values[1] if len(values)>1 else ""
        to = values[2] if len(values)>2 else ""
        cc = values[3] if len(values)>3 else ""
        state,mail_state = classify_invoice(sender,to,cc,user_email=USER_EMAIL)
        out.append({"invoice":inv.get("invoice_number"),"source_row":row,
                    "receipt":mail_state,"ownership":state,
                    "evidence_found":bool(values)})
    return out

def main():
    cred = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    out = audit(AuthorizedSession(cred))
    counts = dict(Counter((r["ownership"],r["receipt"]) for r in out))
    summary = {"month": MONTH, "total_invoices": len(out), "with_mail_evidence":sum(r["evidence_found"] for r in out),
               "direct_css":sum(r["receipt"]=="CSS_DIRECT_RECEIPT" for r in out),
               "other_mail":sum(r["receipt"]!="CSS_DIRECT_RECEIPT" for r in out),
               "owner_verified":0, "owner_mapping_available":False}
    print("CSS_PERSONAL_INVOICE_RECEIPT_AUDIT "+json.dumps(summary,sort_keys=True))
    print("CSS_PERSONAL_INVOICE_RECEIPT_ROWS "+json.dumps(out,sort_keys=True))
    # This script reports recipient provenance, NOT completeness of revenue or ownership.
    # Incomplete evidence is a genuine failure, not a success.
    return 0 if all(r["evidence_found"] for r in out) else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("CSS_PERSONAL_INVOICE_RECEIPT_ERROR "+type(exc).__name__+":"+str(exc)[:180],file=sys.stderr)
        sys.exit(1)
