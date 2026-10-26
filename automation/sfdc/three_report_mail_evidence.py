#!/usr/bin/env python3
"""Contact evidence from quote-email IDs and the user's QQ mail ledger.

Evidence is directional and contact-level, NOT thread-level proof of a resolved
opportunity. Writes only 'SFDC Opportunity Mail Evidence' (generated).
"""
import datetime as dt
import email.utils
import json
import os
import re
import urllib.parse
from collections import defaultdict

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from three_report_email_ingest import SHEET, KST, request, a1, column_name
from three_report_verified_views import replace_generated
from three_report_relationship_qc import read_tab, make_index, field

QQ_SHEET = os.getenv("SFDC_QQ_MAIL_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
OUTPUT = "SFDC Opportunity Mail Evidence"
HEAD = ["Opportunity ID", "Institution", "Stage", "Owner", "Quote Emails",
        "Email Match", "Outbound Messages", "Latest Outbound KST", "Inbound Messages",
        "Latest Inbound KST", "Inbound After Last Outbound", "Contact Evidence",
        "Review Guidance", "Source", "Checked KST"]
OWN_SENDERS = {"taehoon.kim@novogene.com", "masiyuan8900@novogene.com",
               "jiin.yoo@novogene.com"}
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

def addresses(value):
    return {x.lower() for x in EMAIL_PATTERN.findall(str(value or ""))}

def timestamp(value):
    s = str(value or "").strip()
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            return None
        return d.astimezone(KST)
    except ValueError:
        return None

def qq_mail_rows(session, chunk=3000):
    """Bounded source read; only received_at/from/to/cc, not subjects or bodies."""
    root = "https://sheets.googleapis.com/v4/spreadsheets/" + QQ_SHEET
    meta = session.get(root + "?fields=sheets.properties(title,gridProperties.rowCount)", timeout=60)
    if not meta.ok:
        raise RuntimeError("QQ_SHEET_METADATA_HTTP_" + str(meta.status_code))
    props = next((s["properties"] for s in meta.json().get("sheets", [])
                  if s["properties"]["title"] == "All Emails"), None)
    if not props:
        raise RuntimeError("QQ_MAIL_SOURCE_TAB_MISSING")
    bound = min(props["gridProperties"]["rowCount"], 100000)
    for start in range(2, bound + 1, chunk):
        stop = min(bound, start + chunk - 1)
        a = urllib.parse.quote("'All Emails'!C" + str(start) + ":G" + str(stop), safe="")
        result = session.get(root + "/values/" + a, timeout=60)
        if not result.ok:
            raise RuntimeError("QQ_MAIL_READ_HTTP_" + str(result.status_code))
        for row in result.json().get("values", []):
            if row:
                yield row

def latest_events(rows, candidate_emails):
    """Collect precise address evidence, without inferring thread resolution."""
    evidence = defaultdict(lambda: {"out": 0, "in": 0, "last_out": None, "last_in": None})
    for row in rows:
        date = timestamp(row[0] if len(row) > 0 else "")
        if not date:
            continue
        sender = addresses(row[2] if len(row) > 2 else "")
        recipients = addresses(row[3] if len(row) > 3 else "") | addresses(row[4] if len(row) > 4 else "")
        if len(sender) != 1:
            continue
        from_addr = next(iter(sender))
        for address in (recipients & candidate_emails) if from_addr in OWN_SENDERS else (
                {from_addr} & candidate_emails):
            d = evidence[address]
            kind = "out" if from_addr in OWN_SENDERS else "in"
            d[kind] += 1
            key = "last_" + kind
            if d[key] is None or date > d[key]:
                d[key] = date
    return evidence

def build(queue, quotes, mailbox, checked):
    qi = make_index(quotes[0])
    q_to_addresses = defaultdict(set)
    for row in quotes[1:]:
        qid = field(row, qi, "SFDC Quotation ID")
        if qid:
            q_to_addresses[qid].update(addresses(field(row, qi, "Email")))
    qh = make_index(queue[0])
    records = []
    unique_emails = set()
    for row in queue[1:]:
        qids = [v.strip() for v in field(row, qh, "Quote IDs").split("|") if v.strip()]
        emails = set().union(*(q_to_addresses.get(q, set()) for q in qids))
        unique_emails |= emails
        records.append((row, emails))
    event_map = latest_events(mailbox, unique_emails)
    output = [HEAD]
    for row, emails in records:
        history = [event_map[e] for e in emails]
        outbound = sum(h["out"] for h in history)
        inbound = sum(h["in"] for h in history)
        last_out = max((h["last_out"] for h in history if h["last_out"]), default=None)
        last_in = max((h["last_in"] for h in history if h["last_in"]), default=None)
        multiple = len(emails) > 1
        state = ("NO_QUOTE_CUSTOMER_EMAIL" if not emails else
                 "MULTIPLE_CUSTOMER_EMAILS_REVIEW" if multiple else
                 "OUTBOUND_FOUND_REVIEW" if outbound else
                 "INBOUND_ONLY_REVIEW" if inbound else "NO_MAIL_EVIDENCE")
        advice = ("고객 이메일 연결을 확인" if not emails else
                  "복수 연락처 중 실제 담당 고객 확인" if multiple else
                  "마지막 연락의 프로젝트 및 회신 스레드 확인" if outbound or inbound else
                  "이메일 누락·다른 발신자·과거 기록 여부 확인")
        output.append([
            field(row, qh, "Opportunity ID"), field(row, qh, "Institution"),
            field(row, qh, "Stage"), field(row, qh, "Owner"), len(emails),
            "MULTIPLE" if multiple else "UNIQUE" if emails else "MISSING",
            outbound, last_out.isoformat(timespec="seconds") if last_out else "",
            inbound, last_in.isoformat(timespec="seconds") if last_in else "",
            "YES_POSSIBLE_NOT_THREAD_CONFIRMED" if last_in and last_out and last_in > last_out else "NOT_VERIFIED",
            state, advice, "Quote Email + QQ All Emails (exact-address only)", checked
        ])
    return output

def main():
    cred = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(cred)
    queue = read_tab(session, "SFDC Opportunity Review Queue")
    quotes = read_tab(session, "SFDC Email Quotation Raw")
    checked = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    result = build(queue, quotes, qq_mail_rows(session), checked)
    counts = {x: sum(r[11] == x for r in result[1:]) for x in sorted(set(r[11] for r in result[1:]))}
    print("SFDC_CONTACT_EVIDENCE_COUNTS=" + json.dumps(counts, sort_keys=True))
    if os.getenv("SFDC_MAIL_EVIDENCE_APPLY", "false").lower() != "true":
        print("SFDC_CONTACT_EVIDENCE_DRY_RUN=true")
        return
    replace_generated(session, OUTPUT, result)
    print("SFDC_CONTACT_EVIDENCE_TAB_UPDATED=true")

if __name__ == "__main__":
    main()
