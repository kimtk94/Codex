#!/usr/bin/env python3
"""Review-only exact-identifer evidence from QQ email subjects.
Never mark an Opportunity resolved from address or subject similarity.
"""
import datetime as dt
import json
import os
import re
from collections import defaultdict

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from three_report_email_ingest import KST
from three_report_relationship_qc import read_tab, make_index, field
from three_report_mail_evidence import addresses, timestamp, OWN_SENDERS, qq_mail_rows
from three_report_verified_views import replace_generated

TAB = "SFDC Thread Evidence Review"
HEADER = ["Opportunity ID", "Institution", "Stage", "Quote Customer Email Count",
          "Exact ID Outbound", "Exact ID Inbound", "Identifier Type",
          "Evidence Class", "Review Instruction", "Checked KST"]
ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:Opp-\d{4}-\d{2}-\d{2}-\d+|QID-\d{4}-\d{2}-\d{2}-\d+|AMEA\d{8,14})(?![A-Za-z0-9])", re.IGNORECASE)

def build(queue, quotes, mailbox, checked):
    qh, qi = make_index(queue[0]), make_index(quotes[0])
    q_emails = defaultdict(set)
    for r in quotes[1:]:
        key = field(r, qi, "SFDC Quotation ID")
        if key:
            q_emails[key].update(addresses(field(r, qi, "Email")))
    records, token_to_indices = [], defaultdict(set)
    for row in queue[1:]:
        opp = field(row, qh, "Opportunity ID")
        if not opp:
            continue
        qids = [x.strip() for x in field(row, qh, "Quote IDs").split("|") if x.strip()]
        emails = set().union(*(q_emails.get(q, set()) for q in qids))
        tokens = {opp.upper(), *(q.upper() for q in qids)}
        tokens.update(x.upper() for x in ID_PATTERN.findall(field(row, qh, "Opportunity Name")))
        index = len(records)
        records.append({"row": row, "emails": emails, "ids": tokens,
                        "out": 0, "in": 0})
        for token in tokens:
            token_to_indices[token].add(index)
    scanned = 0
    for mail in mailbox:
        scanned += 1
        # C:I gives received_at, from_name, from_email, to, cc, reply_to, subject.
        if len(mail) < 7 or timestamp(mail[0]) is None:
            continue
        ids = {x.upper() for x in ID_PATTERN.findall(mail[6])}
        if not ids:
            continue
        sender = addresses(mail[2])
        if len(sender) != 1:
            continue
        from_email = next(iter(sender))
        outgoing = from_email in OWN_SENDERS
        recipients = addresses(mail[3]) | addresses(mail[4])
        for i in set().union(*(token_to_indices.get(tok, set()) for tok in ids)):
            item = records[i]
            if outgoing and recipients & item["emails"]:
                item["out"] += 1
            elif not outgoing and from_email in item["emails"]:
                item["in"] += 1
    output = [HEADER]
    for item in records:
        row = item["row"]
        hits = item["out"] + item["in"]
        state = ("EXACT_ID_AND_CONTACT_MATCH_REVIEW" if hits else
                 "NO_EXACT_ID_MATCH_NOT_UNANSWERED")
        output.append([field(row, qh, "Opportunity ID"), field(row, qh, "Institution"),
                       field(row, qh, "Stage"), len(item["emails"]), item["out"], item["in"],
                       "Opportunity ID, Quote ID or embedded AMEA",
                       state, "원본 메일의 스레드 및 실제 해결 여부 확인" if hits else
                       "프로젝트 ID가 없는 메일은 증명되지 않음; 미응답으로 간주 금지", checked])
    return output, scanned

def main():
    credential = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(credential)
    queue = read_tab(session, "SFDC Opportunity Review Queue")
    quotes = read_tab(session, "SFDC Email Quotation Raw")
    stamp = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    output, scanned = build(queue, quotes, qq_mail_rows(session), stamp)
    matched = sum(row[4] + row[5] > 0 for row in output[1:])
    print("SFDC_EXACT_THREAD_AUDIT=" + json.dumps({
        "mail_rows_scanned": scanned, "opportunities": len(output)-1,
        "exact_identifier_contact_matches": matched}))
    if os.getenv("SFDC_THREAD_EVIDENCE_APPLY", "false").lower() != "true":
        print("SFDC_THREAD_EVIDENCE_DRY_RUN=true")
        return
    replace_generated(session, TAB, output)
    print("SFDC_THREAD_EVIDENCE_UPDATED=true")

if __name__ == "__main__":
    main()
