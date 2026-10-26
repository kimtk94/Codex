#!/usr/bin/env python3
"""Conservative same-subject evidence, never an automatic reply/close decision."""
import collections
import datetime as dt
import json
import os
import re
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from three_report_email_ingest import KST
from three_report_relationship_qc import read_tab, make_index, field
from three_report_mail_evidence import addresses, timestamp, OWN_SENDERS, qq_mail_rows
from three_report_verified_views import replace_generated

TAB = "SFDC Subject Pair Review"
HEADER = ["Opportunity ID","Institution","Stage","Customer Email Count",
          "Shared Email With Other Opp","Two-way Same Subject Pairs",
          "Inbound After Outbound Pairs","Latest Outbound KST","Latest Inbound KST",
          "Evidence State","Next Review","Checked KST"]

def normalize_subject(value):
    s = str(value or "").strip().lower()
    s = re.sub(r"^(?:(?:re|fw|fwd|회신|전달)\s*[:：]\s*)+", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()

def build(queue, quotes, mailbox, stamp):
    qh, qi = make_index(queue[0]), make_index(quotes[0])
    emails_by_quote = collections.defaultdict(set)
    for row in quotes[1:]:
        key = field(row, qi, "SFDC Quotation ID")
        if key:
            emails_by_quote[key].update(addresses(field(row, qi, "Email")))
    opportunities, owner = [], collections.defaultdict(set)
    for row in queue[1:]:
        oid = field(row, qh, "Opportunity ID")
        if not oid:
            continue
        qids = [x.strip() for x in field(row, qh, "Quote IDs").split("|") if x.strip()]
        emails = set().union(*(emails_by_quote.get(q, set()) for q in qids))
        entry = (oid, field(row, qh, "Institution"), field(row, qh, "Stage"), emails)
        opportunities.append(entry)
        for address in emails:
            owner[address].add(oid)
    pairs = collections.defaultdict(lambda: {"out": 0, "in": 0, "last_out": None, "last_in": None})
    for row in mailbox:
        if len(row) < 7:
            continue
        when = timestamp(row[0])
        sender = addresses(row[2])
        if when is None or len(sender) != 1:
            continue
        src = next(iter(sender))
        outbound = src in OWN_SENDERS
        candidates = (addresses(row[3]) | addresses(row[4])) & owner.keys() if outbound else ({src} & owner.keys())
        if not candidates:
            continue
        subject = normalize_subject(row[6])
        if len(subject) < 12 or subject.startswith(("report results", "your daily digest", "automatic reply", "out of office")):
            continue
        for addr in candidates:
            pair = pairs[(addr, subject)]
            direction = "out" if outbound else "in"
            pair[direction] += 1
            key = "last_" + direction
            if pair[key] is None or when > pair[key]:
                pair[key] = when
    by_opp = collections.defaultdict(list)
    for (addr, _subject), pair in pairs.items():
        if not pair["out"] or not pair["in"]:
            continue
        for oid in owner[addr]:
            by_opp[oid].append(pair)
    result = [HEADER]
    for oid, institution, stage, emails in opportunities:
        matches = by_opp[oid]
        replied = sum(bool(p["last_in"] > p["last_out"]) for p in matches)
        shared = any(len(owner[e]) > 1 for e in emails)
        last_out = max((p["last_out"] for p in matches if p["last_out"]), default=None)
        last_in = max((p["last_in"] for p in matches if p["last_in"]), default=None)
        verdict = ("NO_CONTACT_EMAIL" if not emails else
                   "NO_TWO_WAY_SUBJECT_EVIDENCE" if not matches else
                   "SHARED_EMAIL_AMBIGUOUS" if shared else
                   "SAME_SUBJECT_CANDIDATE_NOT_PROVEN")
        result.append([oid, institution, stage, len(emails),
                       "YES" if shared else "NO", len(matches), replied,
                       last_out.isoformat(timespec="seconds") if last_out else "",
                       last_in.isoformat(timespec="seconds") if last_in else "",
                       verdict, "원본 In-Reply-To/References와 해당 프로젝트 내용 확인 필요", stamp])
    return result

def main():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(creds)
    queue = read_tab(session, "SFDC Opportunity Review Queue")
    quotes = read_tab(session, "SFDC Email Quotation Raw")
    stamp = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    rows = build(queue, quotes, qq_mail_rows(session), stamp)
    summary = {"opportunities": len(rows)-1,
               "two_way_subject_pairs": sum(r[5]>0 for r in rows[1:]),
               "later_inbound_candidates": sum(r[6]>0 for r in rows[1:])}
    print("SFDC_SUBJECT_PAIR_AUDIT=" + json.dumps(summary, sort_keys=True))
    if os.getenv("SFDC_SUBJECT_PAIR_APPLY", "false").lower() == "true":
        replace_generated(session, TAB, rows)
        print("SFDC_SUBJECT_PAIR_GENERATED_TAB_UPDATED=true")
    else:
        print("SFDC_SUBJECT_PAIR_DRY_RUN=true")

if __name__ == "__main__":
    main()
