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
DETAIL_TITLE = "Payment Invoice Match Detail"
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

RECEIPT_GROUPS=((0,2,3),(5,7,6),(9,11,12))
RECEIPT_HEADERS=((0,"Deposit Date"),(2,"Amount (KRW)"),(3,"CMS No."),
                 (5,"Date"),(6,"CMS No. [2]"),(7,"Amount"),
                 (9,"Date [2]"),(11,"Amount [2]"),(12,"CMS No. [3]"))
RECEIPT_NUMBER=re.compile(r"(?<![A-Z0-9])2091(?:25|26)\d{6}(?![A-Z0-9])")

def amount_int(value):
    clean=str(value or "").strip().replace(",","").replace("₩","")
    clean=re.sub(r"\s*KRW\s*$","",clean,flags=re.I).strip()
    if not re.fullmatch(r"\d+(?:\.0+)?",clean):
        return None
    return int(clean.split(".")[0])

def valid_receipt_date(value):
    text=str(value or "").strip()
    if re.fullmatch(r"\d{5}",text):
        day=int(text)
        return 40000 <= day <= 60000
    for fmt in ("%Y-%m-%d","%d-%b-%y","%d-%B-%y",
                "%d-%b-%Y","%d-%B-%Y"):
        try:
            dt.datetime.strptime(text,fmt)
            return True
        except ValueError:
            continue
    return False

def audit_receipt_candidates(receipts,invoice_amounts):
    """Match source CMS numbers for review; NEVER infer bank payment settlement.

    Each source row may contain three independent payment sections, and one
    section may cite multiple invoices. No grouped amount is allocated to
    individual invoices without authoritative allocation evidence.
    """
    if not receipts or len(receipts[0])<13 or any(
        str(receipts[0][i])!=header for i,header in RECEIPT_HEADERS
    ):
        raise RuntimeError("RECEIPT_SOURCE_HEADER_CHANGED")
    references={}
    source_entries=0
    for source_row in receipts[1:]:
        for date_col,amount_col,cms_col in RECEIPT_GROUPS:
            cms=str(source_row[cms_col]) if len(source_row)>cms_col else ""
            numbers=RECEIPT_NUMBER.findall(cms.upper())
            if not numbers:continue
            source_entries+=1
            money=amount_int(source_row[amount_col] if len(source_row)>amount_col else "")
            isdated=valid_receipt_date(source_row[date_col] if len(source_row)>date_col else "")
            for no in set(numbers):
                if no not in invoice_amounts:continue
                references.setdefault(no,[]).append((len(numbers),money,isdated))
    stats=Counter({"RECEIPT_SOURCE_ENTRIES":source_entries,
                   "RECEIPT_LINKED_INVOICE_IDS":len(references)})
    for invoice,records in references.items():
        if len(records)!=1:
            stats["RECEIPT_DUPLICATE_REFERENCE_REVIEW"]+=1
            continue
        group_count,money,isdated=records[0]
        if group_count!=1:
            stats["RECEIPT_GROUPED_ALLOCATION_REVIEW"]+=1
        elif not isdated:
            stats["RECEIPT_DATE_REVIEW"]+=1
        elif money is None or invoice_amounts[invoice] is None:
            stats["RECEIPT_AMOUNT_MISSING_REVIEW"]+=1
        elif money==invoice_amounts[invoice]:
            stats["RECEIPT_EXACT_AMOUNT_CANDIDATE"]+=1
        else:
            stats["RECEIPT_AMOUNT_MISMATCH_REVIEW"]+=1
    # Every matching invoice identifier is classified once.
    if sum(stats[k] for k in (
        "RECEIPT_DUPLICATE_REFERENCE_REVIEW",
        "RECEIPT_GROUPED_ALLOCATION_REVIEW","RECEIPT_DATE_REVIEW",
        "RECEIPT_AMOUNT_MISSING_REVIEW","RECEIPT_EXACT_AMOUNT_CANDIDATE",
        "RECEIPT_AMOUNT_MISMATCH_REVIEW"))!=len(references):
        raise RuntimeError("RECEIPT_CANDIDATE_ACCOUNTING_MISMATCH")
    return stats

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
    if not {SOURCE_INVOICE, SOURCE_FEISHU, "Quote Invoice Ledger",
            "CSS Tax Invoices", "Feishu Latest Receipts"}.issubset(titles):
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
    # Source invoice notification explicitly contains X and H IDs alongside
    # the invoice number; this provides an evidence-backed bridge.
    css = value_range(session, "CSS Tax Invoices", "A1:N2000")
    if not css or css[0][:6] != ["invoice_month", "issued_at", "invoice_number", "amount_krw", "project_id", "h_project_number"]:
        raise RuntimeError("CSS_INVOICE_HEADER_CHANGED")
    invoice_set = {norm(r[0]) for r in invoices[1:] if r and r[0]}
    candidates = {}
    collisions = set()
    for row in css[1:]:
        row = row + [""] * max(0, 12 - len(row))
        inv, h, subject = norm(row[2]), norm(row[5]), str(row[11])
        x_ids = set(re.findall(r"(?<![A-Z0-9])X209SC[0-9]+(?![A-Z0-9])", subject.upper()))
        if inv not in invoice_set or len(x_ids) != 1 or h not in subject.upper() or inv not in norm(subject):
            continue
        x = next(iter(x_ids))
        if inv in candidates and candidates[inv] != (x, h):
            collisions.add(inv)
        candidates[inv] = (x, h)
    for inv in collisions:
        candidates.pop(inv, None)
    stats["INVOICE_X_H_SUBJECT_BRIDGES"] = len(candidates)
    stats["INVOICE_SUBJECT_CONFLICTS"] = len(collisions)
    # Exact X from Feishu project status; bridge must be anchored by invoice number.
    validated_links = sum(x in flags for x, h in candidates.values())
    outstanding_linked = sum(x in flags and len(flags[x]) > 2 and str(flags[x][2]).upper() == "YES"
                            for x, h in candidates.values())
    issued_linked = sum(x in flags and len(flags[x]) > 1 and str(flags[x][1]).upper() == "YES"
                        for x, h in candidates.values())
    # Detailed derived ledger: never equate a project outstanding flag with
    # an invoice-level unpaid balance or received payment.
    evidence_by_invoice = {}
    for row in css[1:]:
        if len(row) > 2 and norm(row[2]) not in evidence_by_invoice:
            evidence_by_invoice[norm(row[2])] = row
    detail = [["Invoice Number", "Institution", "Invoice KRW", "AMEA ID", "CSS H ID",
               "Feishu X ID", "Link Status", "Feishu Outstanding Flag",
               "Feishu eTAX Unissued Flag", "Verified Paid KRW", "Verified Outstanding KRW", "Evidence"]]
    for inv_row in invoices[1:]:
        if not inv_row or not str(inv_row[0]).strip():
            continue
        inv_row = inv_row + [""] * max(0, 16 - len(inv_row))
        number = norm(inv_row[0])
        proof = evidence_by_invoice.get(number, [])
        pair = candidates.get(number)
        x_id = pair[0] if pair else ""
        h_id = pair[1] if pair else ""
        flag = flags.get(x_id) if x_id else None
        status = "EXACT_X_FEISHU_PROJECT" if flag else ("INVOICE_SUBJECT_X_H_ONLY" if pair else "REVIEW_SOURCE_LINK")
        if number in collisions:
            status = "CONFLICT_REVIEW"
        detail.append([
            number, inv_row[4], inv_row[6], inv_row[3],
            h_id, x_id, status,
            str(flag[2]).upper() if flag and len(flag)>2 else "UNKNOWN",
            str(flag[1]).upper() if flag and len(flag)>1 else "UNKNOWN",
            "UNKNOWN", "UNKNOWN",
            "INVOICE_NUMBER_X_H_IN_NOTIFICATION; FEISHU_X_EXACT" if flag else
            ("INVOICE_NUMBER_X_H_IN_NOTIFICATION" if pair else "UNMATCHED_EVIDENCE")
        ])
    if len(detail) - 1 != stats["INVOICES"]:
        raise RuntimeError("DETAIL_INVOICE_COUNT_MISMATCH")
    receipt_rows=value_range(session,"Feishu Latest Receipts","A1:M1000")
    gross_by_invoice={norm(row[0]):amount_int(row[2])
                      for row in detail[1:] if row and row[0]}
    receipt_stats=audit_receipt_candidates(receipt_rows,gross_by_invoice)
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
        ["Invoice-to-Feishu verified links", stats["INVOICE_TO_FEISHU_EXACT_VERIFIED"], "Invoice subject contains matching invoice number, X and H; X is present in Feishu"],
        ["Invoice notification X/H bridges", stats["INVOICE_X_H_SUBJECT_BRIDGES"], "Explicit subject evidence, excludes conflicting invoice IDs"],
        ["Invoice subject conflicts", stats["INVOICE_SUBJECT_CONFLICTS"], "Ambiguous evidence excluded"],
        ["Linked Feishu outstanding flags", stats["LINKED_OUTSTANDING_FLAGS"], "Project flags only: NOT proven unpaid invoice amounts"],
        ["Linked Feishu eTAX unissued flags", stats["LINKED_UNISSUED_FLAGS"], "Review mismatched timing or invoice cycle"],
        ["Invoice-level verified paid count", "UNKNOWN", "Remittance and receipt evidence absent"],
        ["Invoice-level verified collected KRW", "UNKNOWN", "Never interpret as zero"],
        ["Invoice-level verified outstanding KRW", "UNKNOWN", "Never sum project flags as unpaid balances"],
        ["Duplicate invoice keys", stats["DUPLICATE_INVOICE_ID"], "Investigate if nonzero"],
        ["Status", "PAYMENT_PROOF_REQUIRED", "Project flags matched where explicit invoice subject evidence exists; bank remittance still required"],
        ["Source tabs", SOURCE_INVOICE + "; " + SOURCE_FEISHU + "; Quote Invoice Ledger", "No operational source values modified"],
        ["Receipt source entries",receipt_stats["RECEIPT_SOURCE_ENTRIES"],"Three independent payment sections; snapshot only"],
        ["Receipt linked invoice IDs",receipt_stats["RECEIPT_LINKED_INVOICE_IDS"],"Candidate ID overlap; not proof of collection"],
        ["Receipt single-ID exact-amount candidates",receipt_stats["RECEIPT_EXACT_AMOUNT_CANDIDATE"],"Date parses and amount matches, still NOT paid-certified"],
        ["Receipt grouped-allocation review",receipt_stats["RECEIPT_GROUPED_ALLOCATION_REVIEW"],"Several CMS invoice IDs in one source entry; do not distribute amount"],
        ["Receipt duplicate-ID review",receipt_stats["RECEIPT_DUPLICATE_REFERENCE_REVIEW"],"Invoice number appears in multiple source entries; no sum inference"],
        ["Receipt amount mismatch review",receipt_stats["RECEIPT_AMOUNT_MISMATCH_REVIEW"],"Single invoice referenced with differing receipt amount"],
        ["Receipt missing date/amount review",receipt_stats["RECEIPT_DATE_REVIEW"]+receipt_stats["RECEIPT_AMOUNT_MISSING_REVIEW"],"Missing or unparsable source evidence"],
        ["Receipt candidate disposition","REVIEW_ONLY_NOT_PAID","No invoice paid status, cash totals, or original source rows are changed"],
    ]
    if DETAIL_TITLE not in titles:
        request(session, "POST", ":batchUpdate", json={"requests":[{"addSheet":{"properties":{"title":DETAIL_TITLE,"gridProperties":{"rowCount":1000,"columnCount":12,"frozenRowCount":1}}}}]})
    detail_address = urllib.parse.quote("'" + DETAIL_TITLE + "'!A1:L" + str(len(detail)), safe="")
    request(session, "PUT", "/values/" + detail_address + "?valueInputOption=RAW", json={"values":detail})
    if TITLE not in titles:
        request(session, "POST", ":batchUpdate", json={"requests":[{"addSheet":{"properties":{"title":TITLE,"gridProperties":{"rowCount":100,"columnCount":5,"frozenRowCount":2}}}}]})
    address = urllib.parse.quote("'" + TITLE + "'!A1:C" + str(len(out)), safe="")
    request(session, "PUT", "/values/" + address + "?valueInputOption=RAW", json={"values":out})
    print("PAYMENT_RECONCILIATION_QC_PASS invoices=%d projects=%d outstanding_flags=%d verified_invoice_links=%d" %
          (stats["INVOICES"], stats["FEISHU_PROJECTS"], stats["OUTSTANDING_FLAG_PROJECTS"], validated_links))
    print("PAYMENT_RECEIPT_CANDIDATES_REVIEW_ONLY linked=%d exact_candidate=%d grouped=%d duplicates=%d amount_review=%d date_or_missing=%d paid_certified=UNKNOWN" %
          (receipt_stats["RECEIPT_LINKED_INVOICE_IDS"],
           receipt_stats["RECEIPT_EXACT_AMOUNT_CANDIDATE"],
           receipt_stats["RECEIPT_GROUPED_ALLOCATION_REVIEW"],
           receipt_stats["RECEIPT_DUPLICATE_REFERENCE_REVIEW"],
           receipt_stats["RECEIPT_AMOUNT_MISMATCH_REVIEW"],
           receipt_stats["RECEIPT_DATE_REVIEW"]+receipt_stats["RECEIPT_AMOUNT_MISSING_REVIEW"]))
    if stats["DUPLICATE_INVOICE_ID"] or stats["BRIDGE_CONFLICTS"] or stats["INVOICE_SUBJECT_CONFLICTS"]:
        raise RuntimeError("QC_CONFLICT_REVIEW_REQUIRED")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PAYMENT_RECONCILIATION_QC_FAILED " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
