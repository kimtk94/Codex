#!/usr/bin/env python3
"""Read-only cross-table project health audit.

Reads existing evidence projections, not live business-system truth. No
new owner, table, workflow schedule, relationship, amount or status write.
CI emits aggregate fixed-code counts only. A local-only private report is
optional; it contains project keys and diagnostic labels, never customer
names, mail bodies, invoice numbers, document references or amounts.
"""
import argparse
from collections import Counter, defaultdict
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

from project_data_checks import AMEA_RE, X_RE, COVERAGE, CURRENT, HANDOFF
from project_settlement import EVIDENCE_FIELDS, cell, verified_full_payment
from contract_po_tracker import manual_file_verified, parse_time
from sales_home_links import BASE, PROJECT_BOARD

KST = ZoneInfo("Asia/Seoul")
BOARD = "Project Progress Board"
REGISTRY = "X Project Registry"
LINKS = "AMEA H X SAM Link"
INVOICE = "X Invoice Ledger"
PO = "Contract PO Tracker"
MAIL = "Mail Identity 2026"
H_RE = re.compile(r"H\d+SC\d+\Z")
SAM_RE = re.compile(r"(?:SAM\d{11}(?:-[A-Z0-9_]+)?|Z\d{9})\Z")
CMS_RE = re.compile(r"\d{10,15}\Z")
MAIL_RE = re.compile(r"[0-9a-f]{64}\Z")
MINE = "MY_VERIFIED"
CURRENT_RECORD = "CURRENT"
PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 200
# Match the existing mail owner list_all() ceiling, rather than truncate
# the full identity ledger. Other tables keep the tighter bound.
MAIL_MAX_PAGES = 1000
SCHEMAS = {
    BOARD: ("Source Key", "AMEA", COVERAGE, "PM Data Check", "PM Quote Link",
            "PM X Link", "Workflow Lane", "Payment Owner Scope", "Payment State",
            "Completion Evidence", "Invoice Gross KRW", "Outstanding Balance KRW",
            *EVIDENCE_FIELDS),
    REGISTRY: ("Source Key", "X Project", "H Contract", "AMEA", "AMEA Link State",
               "Owner Scope", "Record State"),
    LINKS: ("Source Key", "Link Type", "AMEA", "H Contract", "X Project", "SAM",
            "Link State", "Record State"),
    INVOICE: ("Source Key", "CMS Invoice", "X Base", "X Project", "AMEA", "Owner Scope",
              "Invoice Link State", "Invoice Gross KRW Incl VAT",
              "Outstanding Balance KRW", "Record State"),
    PO: ("Project ID", "Contract Source", "Contract Mail Key", "Contract Notice UTC",
         "PO Status", "PO Followup Queue", "Submission Inference",
         "PO Document Verification", "PO Document Reference", "PO Verified At",
         "PO Verified By"),
    MAIL: ("Mail Key", "Project ID", "Project Link", "Review State",
           "Relationship Status", "Evidence Tier"),
}
NUMERIC_FIELDS = {"Invoice Gross KRW", "Outstanding Balance KRW",
                  "Verified Invoice KRW", "Verified Received KRW",
                  "Invoice Gross KRW Incl VAT"}
MIRRORS = {
    "Online-Project": ("BASE_FIELDS", 48, None),
    "Payment Outstanding": ("HEADER_MATCHED", 72, 45),
    "Payment Receipt": ("HEADER_MATCHED", 72, 45),
    "eTax Invoice": ("HEADER_MATCHED", 72, 45),
    # Proposed advisory bound; not an existing prepayment SLA.
    "Prepayments": ("HEADER_MATCHED", 72, 45),
}
LANES = {"PRODUCTION_ACTIVE", "PAYMENT_FOLLOWUP", "PAID_ARCHIVED"}


class HealthError(RuntimeError):
    pass


def get(row, key):
    return cell(row, key)


def amount(row, key):
    try:
        v = Decimal(get(row, key).replace(",", ""))
        return v if v.is_finite() and v >= 0 else None
    except InvalidOperation:
        return None


def index(rows, key):
    result = {}
    for row in rows:
        value = get(row, key)
        if not value or value in result:
            raise HealthError("HEALTH_DUPLICATE_OR_EMPTY_KEY")
        result[value] = row
    return result


def group(rows, key):
    out = defaultdict(list)
    for row in rows:
        value = get(row, key)
        if value:
            out[value].append(row)
    return out


def current(rows):
    for row in rows:
        state = get(row, "Record State")
        if state not in {CURRENT_RECORD, "SOURCE_NOT_IN_LATEST"}:
            raise HealthError("HEALTH_RECORD_STATE_UNRECOGNIZED")
        if state == CURRENT_RECORD:
            yield row


def manifest_health(rows, now):
    """Metadata age only; neither live source parity nor raw mirror hash."""
    if now.tzinfo is None:
        raise HealthError("HEALTH_CLOCK_TIMEZONE")
    grouped = group(rows, "Source")
    out = {}
    for name, (schema, hours, days) in MIRRORS.items():
        entries = grouped.get(name, [])
        if len(entries) != 1:
            out[name] = {"state": "MISSING_OR_DUPLICATE_MANIFEST"}
            continue
        row = entries[0]
        try:
            stamp = dt.datetime.fromisoformat(get(row, "Synced At KST"))
            date = dt.date.fromisoformat(get(row, "Source Date"))
            n = int(get(row, "Rows"))
            if stamp.tzinfo is None or n <= 0:
                raise ValueError()
            age = (now - stamp).total_seconds() / 3600
            date_age = (now.astimezone(KST).date() - date).days
            if age < 0 or date_age < 0 or date > stamp.astimezone(KST).date():
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            out[name] = {"state": "INVALID_MANIFEST_METADATA"}
            continue
        if get(row, "Schema") != schema or not get(row, "Source ID"):
            state = "SCHEMA_OR_ID_UNVERIFIED"
        elif age > hours or (days is not None and date_age > days):
            state = "OUTSIDE_ADVISORY_LIMIT"
        else:
            state = "WITHIN_METADATA_LIMIT"
        out[name] = {"state": state, "mirror_synced_at_kst": stamp.astimezone(KST).isoformat(),
                     "manifest_source_date": date.isoformat(), "mirror_age_hours": round(age, 2),
                     "source_date_age_days": date_age, "manifest_rows": n,
                     "live_parity": "NOT_RECHECKED"}
    return out


def sfdc_health(rows, now):
    """Report receipt metadata, not Quote Export time or recomputed digest."""
    out = {}
    grouped = group(rows, "Entity")
    for entity in ("Leads", "Opportunities", "Quotation"):
        selected = grouped.get(entity, [])
        if len(selected) != 1:
            out[entity] = {"state": "MISSING_OR_DUPLICATE_REPORT_METADATA"}
            continue
        row = selected[0]
        if (get(row, "Source Kind") != "QQ IMAP"
                or get(row, "State") not in {"STAGED_NOT_PROMOTED", "PRESERVED_NO_NEW_REPORT"}
                or not MAIL_RE.fullmatch(get(row, "Content SHA256"))):
            out[entity] = {"state": "REPORT_METADATA_UNVERIFIED"}
            continue
        try:
            fmt = "%Y-%m-%d %H:%M:%S KST"
            received = dt.datetime.strptime(get(row, "Source Received KST"), fmt).replace(tzinfo=KST)
            checked = dt.datetime.strptime(get(row, "Ingest Checked KST"), fmt).replace(tzinfo=KST)
            if received > checked or checked > now:
                raise ValueError()
            age = (now - received).total_seconds() / 3600
        except (ValueError, TypeError):
            out[entity] = {"state": "REPORT_TIME_UNVERIFIED"}
            continue
        out[entity] = {"state": "RECEIPT_AGE_OVER_6H" if age > 6 else "RECEIPT_WITHIN_6H",
                       "received_at_kst": received.isoformat(),
                       "ingest_checked_at_kst": checked.isoformat(),
                       "receipt_age_hours": round(age, 2), "report_hash": "NOT_RECOMPUTED",
                       "quote_export_time": "NOT_ATTESTED"}
    return out


def po_check(direct, related):
    if direct is None:
        return "RELATED_SCOPE_ONLY" if related else "NO_DIRECT_TRACKER_EVIDENCE"
    if (get(direct, "Contract Source") != "CSS"
            or get(direct, "PO Followup Queue") == "EXCLUDED_NO_OWNER_CONTRACT"):
        return "OUT_OF_OWNER_CONTRACT_SCOPE"
    if not parse_time(get(direct, "Contract Notice UTC")) or not MAIL_RE.fullmatch(get(direct, "Contract Mail Key")):
        return "CONTRACT_EVIDENCE_REVIEW"
    if (get(direct, "Submission Inference") == "CONFLICT_REVIEW"
            or get(direct, "PO Followup Queue") == "PO_EVIDENCE_CONFLICT_REVIEW"
            or get(direct, "PO Status") == "PO_REVIEW"):
        return "CONFLICT_PO_NOTICE"
    if manual_file_verified(direct):
        return "DIRECT_FILE_ATTESTED"
    if get(direct, "PO Document Verification") == "FILE_VERIFIED":
        return "INCOMPLETE_FILE_ATTESTATION"
    if get(direct, "PO Followup Queue") == "PO_SUBMITTED_INFERRED":
        return "DOWNSTREAM_INFERENCE_ONLY"
    if get(direct, "PO Status") in {"PO_RECEIVED_NOTICE", "PO_CONFIRMED_NOTICE"}:
        return "NOTICE_FILE_REVIEW"
    if get(direct, "PO Followup Queue") == "PO_REQUIRED":
        return "TRACKER_REQUEST_REQUIRED"
    return "PO_REVIEW_REQUIRED"


# Fixed codes only: never emit provider-controlled labels or identifiers.
OWNER_SCOPES = {"MY_VERIFIED", "OTHER_SALES", "OWNER_UNVERIFIED"}
X_LINK_CODES = {"EXACT_LIFECYCLE", "UNIQUE_H_CANDIDATE", "AMBIGUOUS_H",
                "X_UNMATCHED", "CONFLICT_MULTIPLE_AMEA", "CONFLICT_LIFECYCLE_CSS_H"}
INVOICE_LINK_CODES = {"EXACT_X_AMEA_CMS", "INVOICE_SOURCE_CONFLICT",
                      "MULTI_Z_REVIEW", "X_NOT_IN_ONLINE",
                      "AMEA_X_NOT_VERIFIED", "AMEA_X_CONFLICT"}


def safe_code(value, allowed):
    return value if value in allowed else "UNCLASSIFIED"


def owner_scope(row):
    return safe_code(get(row, "Owner Scope"), OWNER_SCOPES)


def board_relation(row, pids):
    pid = get(row, "AMEA")
    if pid in pids:
        return "BOARD_PRESENT"
    if not pid:
        return "AMEA_EMPTY"
    return "AMEA_NOT_ON_BOARD" if AMEA_RE.fullmatch(pid) else "AMEA_FORMAT_REVIEW"


def invoice_registry_relation(row, regs, by_base, pids):
    x, base = get(row, "X Project"), get(row, "X Base")
    if not x:
        if not base:
            return "X_BASE_NOT_OBSERVED"
        if not X_RE.fullmatch(base) or re.search(r"-Z\d+$", base):
            return "X_BASE_FORMAT_REVIEW"
        count = len(by_base.get(base, ()))
        return ("X_BASE_NOT_IN_CURRENT_REGISTRY" if not count else
                "X_BASE_MULTIPLE_CURRENT_CANDIDATES" if count > 1 else
                "X_BASE_ONE_CURRENT_CANDIDATE")
    if x not in regs:
        return "X_NOT_IN_CURRENT_REGISTRY"
    registry_amea = get(regs[x], "AMEA")
    if registry_amea and get(row, "AMEA") and registry_amea != get(row, "AMEA"):
        return "X_AMEA_DISAGREEMENT"
    return "X_WITH_BOARD_AMEA" if registry_amea in pids else "X_WITHOUT_BOARD_AMEA"


def orphan_scope_counts(pids, regs, invoices):
    """Observed Board coverage; not a finding of broken lineage or payment."""
    by_base = defaultdict(set)
    for x in regs:
        by_base[re.sub(r"-Z\d+$", "", x)].add(x)
    result = {}
    for kind, records in (("x", regs), ("invoice", invoices)):
        rows = [r for r in records.values() if get(r, "AMEA") not in pids]
        groups = {}
        for scope in ("MY_VERIFIED", "OTHER_SALES", "OWNER_UNVERIFIED", "UNCLASSIFIED"):
            subset = [r for r in rows if owner_scope(r) == scope]
            groups[scope] = {
                "records": len(subset),
                "distinct_valid_amea": len({get(r, "AMEA") for r in subset
                                            if AMEA_RE.fullmatch(get(r, "AMEA"))}),
                "board_relation_counts": dict(Counter(board_relation(r, pids) for r in subset)),
                "link_state_counts": dict(Counter(safe_code(
                    get(r, "AMEA Link State" if kind == "x" else "Invoice Link State"),
                    X_LINK_CODES if kind == "x" else INVOICE_LINK_CODES) for r in subset)),
            }
            if kind == "invoice":
                groups[scope]["registry_relation_counts"] = dict(Counter(
                    invoice_registry_relation(r, regs, by_base, pids) for r in subset))
        result[kind] = {
            "current_records": len(records),
            "board_present": len(records) - len(rows),
            "board_absent": len(rows),
            "owner_scope_counts": dict(Counter(owner_scope(r) for r in records.values())),
            "board_absent_by_owner_scope": groups,
        }
        if sum(v["records"] for v in groups.values()) != len(rows):
            raise HealthError("HEALTH_ORPHAN_SCOPE_COUNT_MISMATCH")
    return result


def review_health(reasons):
    if any(reason.startswith("CONFLICT_") for reason in reasons):
        return "CONFLICT_REVIEW"
    return "REVIEW" if reasons else "LIMITED_OBSERVED_CHECKS_PASS"


def assess(tables, manifest, report_audit, now):
    """Cross-check stored projections. Results are advisory and non-atomic."""
    boards = index(tables[BOARD], "Source Key")
    if not boards:
        raise HealthError("HEALTH_EMPTY_BOARD")
    pids = {}
    for key, row in boards.items():
        pid = get(row, "AMEA")
        if not AMEA_RE.fullmatch(pid) or key != "PROJECT:" + pid or pid in pids:
            raise HealthError("HEALTH_BOARD_IDENTITY_INVALID")
        pids[pid] = row
    reg_all = index(tables[REGISTRY], "Source Key")
    link_all = index(tables[LINKS], "Source Key")
    inv_all = index(tables[INVOICE], "Source Key")
    regs = index(current(reg_all.values()), "X Project")
    links = list(current(link_all.values()))
    invoices = index(current(inv_all.values()), "CMS Invoice")
    pos = index(tables[PO], "Project ID")
    mails = index(tables[MAIL], "Mail Key")
    if any(not X_RE.fullmatch(x) or get(r, "Source Key") != "X:" + x
           for x, r in regs.items()):
        raise HealthError("HEALTH_X_IDENTITY_INVALID")
    if any(not CMS_RE.fullmatch(k) or get(r, "Source Key") != "INVOICE:" + k
           for k, r in invoices.items()):
        raise HealthError("HEALTH_INVOICE_IDENTITY_INVALID")
    if any(not MAIL_RE.fullmatch(k) for k in mails):
        raise HealthError("HEALTH_MAIL_KEY_INVALID")
    regs_by = group(regs.values(), "AMEA")
    links_by = group(links, "AMEA")
    invoices_by = group(invoices.values(), "AMEA")
    mail_by = group(mails.values(), "Project ID")
    h_owner, x_owner, sam_owner = defaultdict(set), defaultdict(set), defaultdict(set)
    h_x = set()
    x_hs, sam_targets = defaultdict(set), defaultdict(set)
    for l in links:
        kind = get(l, "Link Type")
        pid, h, x, sam = (get(l, k) for k in ("AMEA", "H Contract", "X Project", "SAM"))
        if kind == "AMEA_H" and get(l, "Link State") == "EXACT_CSS":
            if AMEA_RE.fullmatch(pid) and H_RE.fullmatch(h):
                h_owner[h].add(pid)
        elif kind == "H_X" and get(l, "Link State") == "EXACT_FEISHU_ONLINE":
            if H_RE.fullmatch(h) and X_RE.fullmatch(x):
                h_x.add((h, x))
                x_hs[x].add(h)
        elif kind == "AMEA_X" and AMEA_RE.fullmatch(pid) and X_RE.fullmatch(x):
            x_owner[x].add(pid)
        elif kind == "AMEA_SAM" and AMEA_RE.fullmatch(pid) and SAM_RE.fullmatch(sam):
            sam_owner[sam].add(pid)
            sam_targets[sam].add((pid, x))
    board_invoice_owner = defaultdict(set)
    for pid, board in pids.items():
        if get(board, COVERAGE) == CURRENT and get(board, "Payment Owner Scope") == MINE:
            for cms in get(board, "Payment Invoice No").split(";"):
                if CMS_RE.fullmatch(cms.strip()):
                    board_invoice_owner[cms.strip()].add(pid)
    source = manifest_health(manifest, now)
    reports = sfdc_health(report_audit, now)
    details = []
    for pid, b in sorted(pids.items()):
        coverage = get(b, COVERAGE)
        lane = get(b, "Workflow Lane")
        if coverage != CURRENT or lane not in LANES:
            details.append({"amea": pid, "health": "NOT_CURRENT_OR_UNCLASSIFIED",
                            "reasons": ["BOARD_NOT_CURRENT_OR_UNCLASSIFIED"],
                            "projection_health": "NOT_CURRENT_OR_UNCLASSIFIED",
                            "projection_reasons": ["BOARD_NOT_CURRENT_OR_UNCLASSIFIED"],
                            "source_metadata_status": "NOT_ASSESSED",
                            "source_metadata_reasons": [],
                            "review_basis": "NOT_ASSESSED"})
            continue
        reasons = set()
        metadata_reasons = set()
        data_check = get(b, "PM Data Check")
        quote = get(b, "PM Quote Link")
        if data_check == "CONFLICT" or quote.startswith("CONFLICT_"):
            reasons.add("CONFLICT_BOARD_CONNECTION")
        elif data_check != "CHECKED" or quote != "EXACT_QUOTE_SNAPSHOT":
            reasons.add("REVIEW_BOARD_CONNECTION")
        # Compare all current AMEA-X evidence, never join on a display name.
        project_links = links_by.get(pid, [])
        project_regs = regs_by.get(pid, [])
        referenced = {get(l, "X Project") for l in project_links
                      if get(l, "Link Type") == "AMEA_X"}
        observed = {get(r, "X Project") for r in project_regs}
        exact_x, exact_h = set(), set()
        x_conflict = False
        for x in referenced | observed:
            r = regs.get(x)
            if not r:
                reasons.add("REVIEW_X_MISSING_REGISTRY")
                continue
            h = get(r, "H Contract")
            if (get(r, "AMEA") not in {"", pid}
                    or len(x_owner[x]) > 1 or len(x_hs[x]) > 1
                    or (h_owner[h] and pid not in h_owner[h])
                    or len(h_owner[h]) > 1
                    or get(r, "AMEA Link State").startswith("CONFLICT_")):
                x_conflict = True
                continue
            exact_link = any(get(l, "Link Type") == "AMEA_X"
                             and get(l, "X Project") == x and get(l, "H Contract") == h
                             and get(l, "Link State") == "EXACT_LIFECYCLE"
                             for l in project_links)
            if (get(r, "AMEA") == pid and get(r, "AMEA Link State") == "EXACT_LIFECYCLE"
                    and exact_link and h_owner[h] == {pid} and (h, x) in h_x):
                exact_x.add(x)
                exact_h.add(h)
            else:
                reasons.add("REVIEW_X_CHAIN_INCOMPLETE")
        if x_conflict:
            reasons.add("CONFLICT_X_PARENT")
        x_state = ("CONFLICT" if x_conflict else
                   "EXACT_OBSERVED_CHAIN" if exact_x and exact_x == (referenced | observed)
                   else "CHAIN_REVIEW")
        if x_state == "CHAIN_REVIEW":
            reasons.add("REVIEW_X_CHAIN")
        sam_links = [l for l in project_links if get(l, "Link Type") == "AMEA_SAM"]
        sam_exact = set()
        sam_review = False
        for l in sam_links:
            sam = get(l, "SAM")
            if (not SAM_RE.fullmatch(sam) or sam_owner[sam] != {pid}
                    or sam_targets[sam] != {(pid, get(l, "X Project"))}
                    or len(exact_x) != 1 or get(l, "X Project") not in exact_x
                    or get(l, "Link State") != "EXACT_SINGLE_X_CHAIN"):
                sam_review = True
            else:
                sam_exact.add(sam)
        if sam_review:
            reasons.add("REVIEW_SAM_CHAIN")
        sam_state = ("REVIEW" if sam_review else
                     "EXACT_OBSERVED_SAMPLES" if sam_links else "NOT_OBSERVED")
        po_state = po_check(pos.get(pid), any(key in pos for key in exact_h | exact_x))
        if po_state.startswith("CONFLICT_"):
            reasons.add("CONFLICT_PO_NOTICE")
        elif po_state not in {"DIRECT_FILE_ATTESTED", "NO_DIRECT_TRACKER_EVIDENCE",
                             "OUT_OF_OWNER_CONTRACT_SCOPE"}:
            reasons.add("REVIEW_PO_EVIDENCE")
        linked_mail = mail_by.get(pid, [])
        mail_exact = sum(get(m, "Project Link") == "PROJECT_ID_EXACT"
                         and get(m, "Review State") == "OK"
                         and get(m, "Relationship Status") == "LINKED"
                         and get(m, "Evidence Tier") in {"EXACT_PROJECT_ONLY", "EXACT_CONTACT_AND_PROJECT"}
                         for m in linked_mail)
        mail_review = len(linked_mail) - mail_exact
        if mail_review:
            reasons.add("REVIEW_MAIL_IDENTITY")
        mail_state = ("REVIEW" if mail_review else
                      "EXACT_OBSERVED_MAIL" if mail_exact else "NOT_OBSERVED")
        # Payment information is only inspected/reported within the established
        # owner scope. A missing invoice does not prove "not due" or "paid".
        payment_state = "OUTSIDE_VERIFIED_OWNER_SCOPE"
        if get(b, "Payment Owner Scope") == MINE:
            own = invoices_by.get(pid, [])
            listed = {get(r, "CMS Invoice") for r in own}
            expected = {v.strip() for v in get(b, "Payment Invoice No").split(";") if v.strip()}
            if any(not CMS_RE.fullmatch(v) for v in expected):
                reasons.add("REVIEW_BOARD_INVOICE_ID")
            if any(len(board_invoice_owner[v]) > 1 for v in expected):
                reasons.add("CONFLICT_SHARED_BOARD_INVOICE")
            exact = [r for r in own if get(r, "Owner Scope") == MINE
                     and get(r, "Invoice Link State") == "EXACT_X_AMEA_CMS"
                     and get(r, "X Project") in exact_x]
            full = bool(own) and len(exact) == len(own) and listed == expected
            if any(get(r, "Invoice Link State") in {"INVOICE_SOURCE_CONFLICT", "AMEA_X_CONFLICT"}
                   or get(r, "Owner Scope") == "OTHER_SALES" for r in own):
                reasons.add("CONFLICT_INVOICE_LINK")
            if not full:
                reasons.add("REVIEW_INVOICE_SET_OR_CHAIN")
            gross = [amount(r, "Invoice Gross KRW Incl VAT") for r in exact]
            board_gross = amount(b, "Invoice Gross KRW")
            if full:
                if board_gross is None or any(v is None for v in gross):
                    reasons.add("REVIEW_INVOICE_AMOUNT")
                elif sum(gross, Decimal("0")) != board_gross:
                    reasons.add("CONFLICT_INVOICE_GROSS")
                balances = [amount(r, "Outstanding Balance KRW") for r in exact]
                board_balance = amount(b, "Outstanding Balance KRW")
                if all(v is not None for v in balances) and board_balance is not None:
                    if sum(balances, Decimal("0")) != board_balance:
                        reasons.add("CONFLICT_INVOICE_BALANCE")
                elif board_balance is not None:
                    reasons.add("REVIEW_INVOICE_BALANCE_COVERAGE")
            positive = any((amount(r, "Outstanding Balance KRW") or Decimal("0")) > 0
                           for r in exact)
            if lane == "PAID_ARCHIVED" and (positive or (amount(b, "Outstanding Balance KRW") or Decimal("0")) > 0):
                reasons.add("CONFLICT_ARCHIVE_POSITIVE_BALANCE")
            if lane == "PAID_ARCHIVED":
                if get(b, "Completion Evidence") not in HANDOFF:
                    reasons.add("REVIEW_ARCHIVE_HANDOFF")
                if not verified_full_payment(b):
                    reasons.add("REVIEW_ARCHIVE_RECEIPT")
                elif board_gross is not None and amount(b, "Verified Invoice KRW") != board_gross:
                    reasons.add("CONFLICT_ARCHIVE_RECEIPT_GROSS")
                if get(b, "Receipt Source") == "FEISHU_LATEST_PAYMENT_RECEIPT":
                    for field, name in (
                            ("Receipt Source Snapshot Date", "Payment Receipt"),
                            ("Outstanding Source Snapshot Date", "Payment Outstanding")):
                        observed_date = source[name].get("manifest_source_date")
                        if observed_date and get(b, field) != observed_date:
                            reasons.add("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT")
                        if not observed_date or source[name]["state"] != "WITHIN_METADATA_LIMIT":
                            metadata_reasons.add("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT")
            payment_state = ("EXACT_OBSERVED_INVOICE_SET" if full and not any(
                "INVOICE" in r or "ARCHIVE" in r for r in reasons | metadata_reasons)
                else "INVOICE_OR_RECEIPT_REVIEW")
        elif lane == "PAYMENT_FOLLOWUP":
            reasons.add("REVIEW_PAYMENT_OWNER_SCOPE")
        # Metadata warnings are an independent axis: a shared stale report
        # must not masquerade as hundreds of separate project defects.
        # Keep the original combined health conservative for compatibility.
        if source["Online-Project"]["state"] != "WITHIN_METADATA_LIMIT":
            metadata_reasons.add("REVIEW_ONLINE_MIRROR_METADATA")
        if get(b, "Payment Owner Scope") == MINE and any(
                source[name]["state"] != "WITHIN_METADATA_LIMIT"
                for name in ("Payment Outstanding", "Payment Receipt", "eTax Invoice")):
            metadata_reasons.add("REVIEW_FINANCE_MIRROR_METADATA")
        if source["Prepayments"]["state"] != "WITHIN_METADATA_LIMIT":
            metadata_reasons.add("REVIEW_PREPAYMENT_MIRROR_METADATA")
        if reports["Quotation"]["state"] != "RECEIPT_WITHIN_6H":
            metadata_reasons.add("REVIEW_QUOTE_REPORT_RECEIPT_METADATA")
        combined = reasons | metadata_reasons
        basis = ("BOTH" if reasons and metadata_reasons else
                 "PROJECT_ONLY" if reasons else
                 "SOURCE_METADATA_ONLY" if metadata_reasons else
                 "NO_OBSERVED_REVIEW")
        details.append({"amea": pid, "health": review_health(combined),
                        "projection_health": review_health(reasons),
                        "projection_reasons": sorted(reasons),
                        "source_metadata_status": ("ADVISORY_REVIEW" if metadata_reasons
                                                   else "WITHIN_CHECKED_METADATA_LIMITS"),
                        "source_metadata_reasons": sorted(metadata_reasons),
                        "review_basis": basis,
                        "x_chain": x_state,
                        "x_exact_count": len(exact_x), "sam_chain": sam_state,
                        "sam_exact_count": len(sam_exact), "po": po_state,
                        "mail": mail_state, "mail_exact_count": mail_exact,
                        "invoice": payment_state, "reasons": sorted(combined)})
    summary = {
        "checked_at_kst": now.astimezone(KST).isoformat(),
        "mode": "READ_ONLY_NON_ATOMIC_PROJECTION_AUDIT",
        "project_counts": dict(Counter(d["health"] for d in details)),
        "reason_counts": dict(Counter(r for d in details for r in d["reasons"])),
        "projection_counts": dict(Counter(d["projection_health"] for d in details)),
        "projection_reason_counts": dict(Counter(r for d in details for r in d["projection_reasons"])),
        "source_metadata_project_counts": dict(Counter(d["source_metadata_status"] for d in details)),
        "source_metadata_reason_counts": dict(Counter(r for d in details for r in d["source_metadata_reasons"])),
        "review_basis_counts": dict(Counter(d["review_basis"] for d in details)),
        "mirror_metadata": source, "sfdc_receipt_metadata": reports,
        "source_freshness_unattested": ["CSS", "Lifecycle", "PO Tracker", "Mail Identity",
                                      "X Registry", "SFDC Quote Export"],
        "unassigned_current_x": sum(get(r, "AMEA") not in pids for r in regs.values()),
        "unassigned_current_invoices": sum(get(r, "AMEA") not in pids for r in invoices.values()),
        "board_coverage_by_owner": orphan_scope_counts(pids, regs, invoices),
        "mail_without_board_project": sum(get(r, "Project ID") not in pids for r in mails.values()),
        "business_writes": 0,
    }
    return summary, details


def strict_pages(api, token, path, action, max_pages=DEFAULT_MAX_PAGES):
    """Complete bounded reads, refusing malformed pages/cursor cycles."""
    rows, cursor, seen, total = [], "", set(), None
    for _ in range(max_pages):
        qs = urllib.parse.urlencode({"page_size": PAGE_SIZE, **({"page_token": cursor} if cursor else {})})
        data = api("GET", path + "?" + qs, token, action=action)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or type(data.get("has_more")) is not bool:
            raise HealthError("HEALTH_PAGE_SCHEMA")
        if len(data["items"]) > PAGE_SIZE or any(not isinstance(row, dict) for row in data["items"]):
            raise HealthError("HEALTH_PAGE_SCHEMA")
        if "total" in data:
            n = data["total"]
            if type(n) is not int or n < 0 or (total is not None and n != total):
                raise HealthError("HEALTH_PAGE_TOTAL_CHANGED")
            if n > max_pages * PAGE_SIZE:
                raise HealthError("HEALTH_PAGE_BOUND_EXCEEDED")
            total = n
        rows.extend(data["items"])
        if data["has_more"] is False:
            if total is not None and len(rows) != total:
                raise HealthError("HEALTH_PAGE_COUNT_MISMATCH")
            return rows
        cursor = data.get("page_token")
        if not isinstance(cursor, str) or not cursor or cursor in seen or not data["items"]:
            raise HealthError("HEALTH_PAGE_CURSOR")
        seen.add(cursor)
    raise HealthError("HEALTH_PAGE_BOUND_EXCEEDED")


def read_tables(api, token, root):
    catalog = group(strict_pages(api, token, root+"/tables", "health_tables"), "name")
    output = {}
    for name, required in SCHEMAS.items():
        matches = catalog.get(name, [])
        if len(matches) != 1:
            raise HealthError("HEALTH_TABLE_MISSING_OR_AMBIGUOUS")
        tid = get(matches[0], "table_id")
        if not re.fullmatch(r"tbl[A-Za-z0-9]+", tid) or (name == BOARD and tid != PROJECT_BOARD):
            raise HealthError("HEALTH_TABLE_ID_UNVERIFIED")
        path = root+"/tables/"+urllib.parse.quote(tid, safe="")
        fields = group(strict_pages(api, token, path+"/fields", "health_fields"), "field_name")
        if any(len(fields.get(k, [])) != 1 or fields[k][0].get("type") !=
               (2 if k in NUMERIC_FIELDS else 1) for k in required):
            raise HealthError("HEALTH_FIELD_SCHEMA_UNVERIFIED")
        records = strict_pages(api, token, path+"/records", "health_records",
                               max_pages=MAIL_MAX_PAGES if name == MAIL else DEFAULT_MAX_PAGES)
        index(records, "record_id")
        selected = []
        for record in records:
            raw = record.get("fields")
            if not isinstance(raw, dict):
                raise HealthError("HEALTH_RECORD_SCHEMA")
            # Drop completely blank default records only; nonblank unkeyed
            # business rows must fail the subsequent identity checks.
            if not any(get(raw, k) for k in raw):
                continue
            selected.append({k: get(raw, k) for k in required})
        output[name] = selected
    return output


def local_report(path, summary, details):
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise HealthError("HEALTH_PRIVATE_REPORT_FORBIDDEN_IN_CI")
    target = Path(path).expanduser()
    repo = Path(__file__).resolve().parents[2]
    if not target.is_absolute() or target.resolve().is_relative_to(repo):
        raise HealthError("HEALTH_PRIVATE_REPORT_OUTSIDE_REPO_REQUIRED")
    # No overwrite, no symlink target, no directory creation.
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "projects": details}, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-report", help="Local-only absolute new file outside repository")
    args = parser.parse_args()
    if args.private_report and (os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
        raise HealthError("HEALTH_PRIVATE_REPORT_FORBIDDEN_IN_CI")
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != BASE:
        raise HealthError("HEALTH_REFUSE_OTHER_BASE")
    from qq_mail_ingest import auth, api
    from sales_metrics_sync import sheets_session, req_sheet, UNIFIED_SHEET
    started = dt.datetime.now(KST)
    token, root = auth()
    tables = read_tables(api, token, root)
    session = sheets_session()
    manifest = req_sheet(session, UNIFIED_SHEET, "Feishu Source Manifest", 20)
    report_audit = req_sheet(session, UNIFIED_SHEET, "SFDC Email Ingest Audit", 30)
    if len(manifest) >= 19 or len(report_audit) >= 29:
        raise HealthError("HEALTH_METADATA_RANGE_BOUND")
    now = dt.datetime.now(KST)
    summary, details = assess(tables, manifest, report_audit, now)
    summary["read_started_at_kst"] = started.isoformat()
    if args.private_report:
        local_report(args.private_report, summary, details)
    print("PROJECT_HEALTH_AUDIT " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("PROJECT_HEALTH_READ_COMPLETED business_writes=0 source_freshness_certified=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Only fixed error codes from this module; never print raw provider errors.
        print("PROJECT_HEALTH_FAILED " + (str(exc) if isinstance(exc, HealthError)
                                           else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
