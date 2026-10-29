#!/usr/bin/env python3
"""Four-track sales automation release gate: STRICTLY read-only Sheet checks.

No mail sending, SFDC Save, Sheets writes, Decision edits or logging PII.
Usage: python automation/ops/sales_parallel_readonly_audit.py lead|revenue
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
from decimal import Decimal

import google.auth
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
SCOPE = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
KST = dt.timezone(dt.timedelta(hours=9))
VALID = {"SENT_AFTER_LEAD_CONFIRMED", "SENT_BEFORE_LEAD_ONLY", "NO_PERSONAL_OUTBOUND_EVIDENCE"}
SKIP = {"QUALIFIED", "CONVERTED", "CLOSED", "UNQUALIFIED"}


def credentials():
    raw = os.environ.get("CKD_DRIVE_SA_JSON") or os.environ.get("NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("MISSING_READONLY_SHEETS_CREDENTIAL")
    try:
        j = json.loads(raw)
    except (ValueError, TypeError):
        j = json.loads(base64.b64decode(raw))
    return service_account.Credentials.from_service_account_info(j, scopes=SCOPE)


class Reader:
    def __init__(self):
        self.session = AuthorizedSession(credentials())

    def rows(self, tab, area):
        a1 = "'" + tab.replace("'", "''") + "'!" + area
        url = "https://sheets.googleapis.com/v4/spreadsheets/" + BOOK + "/values/" + __import__("urllib.parse", fromlist=["quote"]).quote(a1, safe="")
        response = self.session.get(url, params={"valueRenderOption": "FORMATTED_VALUE"}, timeout=45)
        response.raise_for_status()
        return response.json().get("values", [])


def cell(r, i):
    return str(r[i]).strip() if len(r) > i and r[i] is not None else ""


def tab(rows, required, key):
    if not rows or not all(name in rows[0] for name in required):
        raise ValueError("SCHEMA_MISMATCH_" + key)
    h = rows[0]
    return [dict(zip(h, r + [""] * (len(h) - len(r)))) for r in rows[1:] if r]


def num(s):
    v = re.sub(r"[₩,\s]", "", str(s or ""))
    if not v or not re.fullmatch(r"-?\d+(?:\.\d+)?", v):
        raise ValueError("INVALID_CURRENCY_VALUE")
    return Decimal(v)


def iso(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("INVALID_SOURCE_TIMESTAMP") from e


def run_lead(r, now):
    ingest = tab(r.rows("SFDC Email Ingest Audit", "A1:J20"),
                 ["Entity", "Rows", "Unique IDs", "Missing IDs", "State"], "INGEST")
    by = {x["Entity"]: x for x in ingest}
    for label in ("Leads", "Opportunities", "Quotation"):
        if label not in by or by[label]["State"] != "STAGED_NOT_PROMOTED":
            raise ValueError("UNVERIFIED_REPORT_" + label)
        if num(by[label]["Missing IDs"]) != 0:
            raise ValueError("REPORT_MISSING_IDS_" + label)
        date = dt.datetime.strptime(by[label]["Ingest Checked KST"], "%Y-%m-%d %H:%M:%S KST").replace(tzinfo=KST)
        if not dt.timedelta(0) <= now - date <= dt.timedelta(hours=72):
            raise ValueError("STALE_REPORT_" + label)
    raw = tab(r.rows("SFDC Email Leads Raw", "A1:W700"), ["SFDC Lead ID"], "LEADS")
    actual = {x.get("SFDC Lead ID", "").strip() for x in raw if x.get("SFDC Lead ID")}
    if len(actual) != len(raw) or len(actual) != int(num(by["Leads"]["Unique IDs"])):
        raise ValueError("REPORT_LEAD_ID_PARITY")
    audit = tab(r.rows("Lead My Sent Audit", "A1:T700"),
                ["Lead ID", "My Mail Status", "Description Class", "Latest QQ Outbound Checked"], "PERSONAL")
    ids = {x["Lead ID"].strip() for x in audit if x.get("Lead ID")}
    if actual != ids or len(audit) != len(ids):
        raise ValueError("PERSONAL_LEAD_ID_PARITY")
    latest = {x["Latest QQ Outbound Checked"] for x in audit}
    if len(latest) != 1:
        raise ValueError("QQ_LATEST_UNSTABLE")
    qq_ts = iso(next(iter(latest))).astimezone(KST)
    if not dt.timedelta(0) <= now - qq_ts <= dt.timedelta(hours=72):
        raise ValueError("QQ_SOURCE_STALE")
    states = {name: sum(x["My Mail Status"] == name for x in audit) for name in VALID}
    if any(x["My Mail Status"] not in VALID for x in audit) or sum(states.values()) != len(audit):
        raise ValueError("UNCLASSIFIED_MAIL_STATUS")
    pool = tab(r.rows("NBA Action Pool", "A1:N2000"),
               ["Source", "Record ID", "Verification"], "NBA_POOL")
    leads = [x for x in pool if x.get("Source") == "LEAD"]
    present = {x["Record ID"] for x in leads}
    if len(present) != len(leads):
        raise ValueError("NBA_LEAD_DUPLICATE")
    actionable = {x["Lead ID"] for x in audit
                  if x["My Mail Status"] != "SENT_AFTER_LEAD_CONFIRMED"
                  and x.get("Lead Status", "").upper() not in SKIP and not x.get("Opportunity ID")}
    if present != actionable:
        raise ValueError("NBA_PERSONAL_LEAD_QUEUE_PARITY")
    expected = {x["Lead ID"]: x["My Mail Status"] for x in audit}
    if any(x["Verification"] != expected[x["Record ID"]] for x in leads):
        raise ValueError("NBA_LEAD_EVIDENCE_MISMATCH")
    print("TRACK_A_LEAD_PASS " + json.dumps({
        "raw_leads": len(actual),
        "opportunities": int(num(by["Opportunities"]["Unique IDs"])),
        "quotes_unique": int(num(by["Quotation"]["Unique IDs"])),
        "sent_after": states["SENT_AFTER_LEAD_CONFIRMED"],
        "prior_only": states["SENT_BEFORE_LEAD_ONLY"],
        "never": states["NO_PERSONAL_OUTBOUND_EVIDENCE"],
        "nba_lead_candidates": len(leads)}, sort_keys=True))
    return True


def run_revenue(r, now):
    rows = tab(r.rows("BI Revenue Lifecycle Monthly", "A1:Q24"),
               ["Month", "Actual Invoice KRW", "Pending Verified KRW", "Forecast KRW",
                "Combined KRW (verified + estimate)", "Verified Billing KRW (Actual + Pending)",
                "Invoice kUSD (KRW@FX)", "Verified Pending kUSD (KRW@FX)",
                "Verified Billing kUSD (A+P)"], "REVENUE")
    health = r.rows("Automation Health", "A1:D40")
    status = {cell(x, 0): cell(x, 2) for x in health}
    if status.get("Revenue Lifecycle") != "PASS" or status.get("Verified Billing FX Parity") != "PASS":
        raise ValueError("REVENUE_SOURCE_NOT_PASS")
    for x in rows:
        if not re.fullmatch(r"\d{4}-\d{2}", x.get("Month", "")):
            continue
        a, p, f = (num(x[k]) for k in ("Actual Invoice KRW", "Pending Verified KRW", "Forecast KRW"))
        combined = num(x["Combined KRW (verified + estimate)"])
        verified = num(x["Verified Billing KRW (Actual + Pending)"])
        if min(a, p, f) < 0 or a+p+f != combined or a+p != verified:
            raise ValueError("REVENUE_DOUBLE_COUNT_OR_SUM_MISMATCH")
        fx_fields = ("Invoice kUSD (KRW@FX)", "Verified Pending kUSD (KRW@FX)",
                     "Verified Billing kUSD (A+P)")
        fx_values = [num(x[k]) for k in fx_fields]
        for amount, shown in zip((a, p, verified), fx_values):
            # kUSD = KRW / 1_500_000, rounded to three decimals.
            if abs(shown - amount / Decimal(1500000)) > Decimal("0.002"):
                raise ValueError("REVENUE_FX_MISMATCH")
        if num(x.get("Pending Amount Unknown", "0")):
            raise ValueError("UNVERIFIED_PENDING_AMOUNT")
    octo = next((x for x in rows if x.get("Month") == now.strftime("%Y-%m")), None)
    if not octo:
        raise ValueError("CURRENT_MONTH_REVENUE_MISSING")
    print("TRACK_B_REVENUE_PASS " + json.dumps({
        "month": octo["Month"], "invoice": str(num(octo["Actual Invoice KRW"])),
        "pending": str(num(octo["Pending Verified KRW"])),
        "forecast": str(num(octo["Forecast KRW"])),
        "verified_billing": str(num(octo["Verified Billing KRW (Actual + Pending)"]))}, sort_keys=True))
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("track", choices=("lead", "revenue"))
    args = p.parse_args()
    r = Reader()
    now = dt.datetime.now(KST)
    if args.track == "lead":
        run_lead(r, now)
    else:
        run_revenue(r, now)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print("SALES_PARALLEL_CHECK_FAILED: " + str(error).split("\n")[0], file=sys.stderr)
        sys.exit(1)
