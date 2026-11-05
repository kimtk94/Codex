#!/usr/bin/env python3
"""Read-only aggregate audit of unlinked 2026 QQ mail from the NEW Feishu Base.

Source mail comes from Feishu QQ Mail Intake, never Google Sheets. Existing
SFDC/Project sheets are matching references only. No private addresses, subject
lines, message IDs, record IDs, or individual records are printed.

Output is deliberately counts and overlap statistics: can guide later updates
without silently attaching an email to the wrong customer or project.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

from qq_mail_ingest import auth, find_table, list_all, plain_field, SMOKE_KEY, SafeError
from mail_classification_2026 import email_set, since_2026, CSS
from mail_identity_2026 import (
    build_index, decorate, load_references, mail_contact, mail_project,
    PROJECT_RE, H_RE, KST,
)

DIRECTION = ("INBOUND", "OUTBOUND")
PERSONAL_DOMAINS = {
    "gmail.com", "naver.com", "daum.net", "hanmail.net", "kakao.com",
    "outlook.com", "hotmail.com", "yahoo.com", "qq.com", "163.com",
    "icloud.com", "me.com", "live.com", "msn.com",
}


def internal_only(sender, recipients):
    addresses = set(sender) | set(recipients)
    if not addresses:
        return False
    return all(x.rsplit("@",1)[-1] == "novogene.com" or
               x.rsplit("@",1)[-1] == "novogene-amea.com"
               for x in addresses if "@" in x)


def messages(rows, idx, now):
    source = []
    keys = set()
    for record in rows:
        f = {k:plain_field(v) for k,v in (record.get("fields") or {}).items()}
        key=f.get("Mail Key","")
        if key==SMOKE_KEY:
            continue
        if not key or key in keys:
            raise SafeError("AUDIT_BAD_OR_DUPLICATE_MAIL_KEY")
        keys.add(key)
        if not since_2026(f.get("Received At")):
            continue
        source.append((f, decorate(f,idx,now)))
    return source


def unique_linked_parent(parent_id, by_message_id, relationships):
    # Refuse unknown/duplicated Message-ID and unverified parent links.
    if not parent_id:
        return None
    parents=by_message_id.get(parent_id.strip().lower(), [])
    if len(parents)!=1:
        return None
    record=relationships[parents[0]]
    if record["Review State"]=="REVIEW" or record["Relationship Status"]!="LINKED":
        return None
    if record["Project Link"]!="PROJECT_ID_EXACT":
        return None
    return record


def summarize(src, idx):
    counter = collections.Counter()
    linked_by_message_id = collections.defaultdict(list)
    identity = {}
    for mail, relation in src:
        key = mail["Mail Key"]
        identity[key] = relation
        mid = mail.get("Message ID", "").strip().lower()
        if mid:
            linked_by_message_id[mid].append(key)
    for mail, relation in src:
        state=relation["Relationship Status"]
        direction=mail.get("Direction","")
        sender=email_set(mail.get("From"))
        recipients=email_set(mail.get("To"))|email_set(mail.get("CC"))
        css = CSS in sender and direction=="INBOUND"
        category=relation["Primary Category"]
        counter["TOTAL_2026"]+=1
        counter["STATE_"+state]+=1
        counter["DIRECTION_"+direction]+=1
        counter["CATEGORY_"+category]+=1
        if state!="UNMATCHED":
            continue
        counter["UNMATCHED_CATEGORY_"+category]+=1
        counter["UNMATCHED_DIRECTION_"+direction]+=1
        if css:
            counter["UNMATCHED_CSS"]+=1
        elif category=="SYSTEM_REPORT":
            counter["UNMATCHED_SYSTEM_REPORT"]+=1
        elif internal_only(sender,recipients):
            counter["UNMATCHED_INTERNAL_ONLY"]+=1
        else:
            counter["UNMATCHED_EXTERNAL_OTHER"]+=1
        if not mail.get("Subject"):
            counter["UNMATCHED_EMPTY_SUBJECT"]+=1
        if not mail.get("Body Excerpt"):
            counter["UNMATCHED_EMPTY_BODY_EXCERPT"]+=1
        primary_correspondents = (sender-{CSS}) if direction=="INBOUND" else recipients
        known = [x for x in primary_correspondents if idx["contacts"].get(x)]
        lead = [x for x in primary_correspondents if idx["leads"].get(x)]
        if known:
            counter["UNMATCHED_HAS_CONTACT_EMAIL_REFERENCE"]+=1
        elif lead:
            counter["UNMATCHED_HAS_LEAD_EMAIL_REFERENCE"]+=1
        else:
            counter["UNMATCHED_NO_EMAIL_REFERENCE"]+=1
        subject=(mail.get("Subject") or "").upper()
        body=(mail.get("Body Excerpt") or "").upper()
        subject_ids=set(PROJECT_RE.findall(subject))|set(H_RE.findall(subject))
        body_ids=set(PROJECT_RE.findall(body))|set(H_RE.findall(body))
        if not subject_ids:
            counter["UNMATCHED_NO_SUBJECT_PROJECT_ID"]+=1
        if body_ids and not subject_ids:
            counter["UNMATCHED_BODY_ONLY_PROJECT_CANDIDATE"]+=1
            possible=set()
            for ident in body_ids:
                for candidate in idx["projects"].get(ident,[]) if ident.startswith("AMEA") else idx["h_ids"].get(ident,[]):
                    possible.add(candidate.get("project_id"))
            if len(possible)==1:
                counter["UNMATCHED_BODY_ONLY_ONE_PROJECT_CANDIDATE"]+=1
            elif len(possible)>1:
                counter["UNMATCHED_BODY_ONLY_MULTIPLE_PROJECTS"]+=1
        # A parent match is a review candidate, never an inferred identity.
        parent=unique_linked_parent(mail.get("In Reply To"),linked_by_message_id,identity)
        if parent:
            counter["UNMATCHED_EXACT_PARENT_PROJECT_CANDIDATE"]+=1
        # Unique domain account coverage is diagnostic only; generic/department
        # emails and domain synonyms are not customer identity proof.
        domain_accounts=collections.defaultdict(set)
        for address, contacts in idx["contacts"].items():
            domain=address.rsplit("@",1)[-1] if "@" in address else ""
            if domain and domain not in PERSONAL_DOMAINS:
                for contact in contacts:
                    if contact.get("account"):
                        domain_accounts[domain].add(contact["account"])
        domains={a.rsplit("@",1)[-1] for a in primary_correspondents if "@" in a}
        candidates={tuple(domain_accounts[d]) for d in domains if len(domain_accounts[d])==1}
        if len(candidates)==1:
            counter["UNMATCHED_UNIQUE_DOMAIN_ACCOUNT_CANDIDATE"]+=1
    return dict(sorted(counter.items()))


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN","").strip() != "IpMkbUD0vaFqtYs93a3csXtdn1b":
        raise SafeError("AUDIT_REFUSE_OTHER_BASE")
    token,root=auth()
    tid=find_table(token,root)
    if not tid:
        raise SafeError("MAIL_INTAKE_MISSING")
    path=root+"/tables/"+urllib.parse.quote(tid,safe="")+"/records"
    records=list_all(path,token,"identity_gap_mail_read")
    references=load_references()
    idx=build_index(references)
    rows=messages(records,idx,dt.datetime.now(KST))
    metrics=summarize(rows,idx)
    print("IDENTITY_GAP_AUDIT="+json.dumps(metrics,sort_keys=True))
    print("IDENTITY_GAP_AUDIT_PASS mail_writes=0 sheet_writes=0 private_payload_logs=0")


if __name__=="__main__":
    try:
        main()
    except Exception as error:
        reason=str(error) if isinstance(error, SafeError) else type(error).__name__
        print("IDENTITY_GAP_AUDIT_FAILED:"+reason,file=sys.stderr)
        sys.exit(1)
