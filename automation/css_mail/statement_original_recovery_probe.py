#!/usr/bin/env python3
"""Read-only bounded QQ original recovery probe; no row-level outputs.

Only the original INBOX UID candidates from fully read staging are fetched.
No writes to Sheets, mail, Salesforce or Feishu. A parsed amount is a
recovered source candidate; this command does not publish Actual/Pending.
"""
from collections import Counter,defaultdict
import datetime as dt
from decimal import Decimal,InvalidOperation
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses,parsedate_to_datetime
import imaplib
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

from statement_source_coverage import read_full_source, select_candidates, exact_key, ready, ISSUE, instant
from tax_invoice_extract import extract, bodystructure_filenames, imap_bodystructure_chunks, HEADER
from pending_statement_uid_amounts import textparts

KST=ZoneInfo("Asia/Seoul")
MAX_ITEMS=20
MAX_BYTES=12*1024*1024
TOTAL=re.compile(r"Total\s*Amount\b\s*[:：]?\s*(?:(KRW|USD)\s*([0-9][0-9,]*(?:\.\d{1,2})?)\b|([0-9][0-9,]*(?:\.\d{1,2})?)\s*(KRW|USD)\b)",re.I)


def statement_total(msg):
    found=set()
    for text in textparts(msg):
        for m in TOTAL.finditer(text):
            currency=(m.group(1) or m.group(4)).upper()
            try:
                amount=Decimal((m.group(2) or m.group(3)).replace(",",""))
            except InvalidOperation:
                return None
            if not amount.is_finite() or amount<=0:
                return None
            found.add((currency,amount))
    if len(found)!=1:
        return None
    currency,amount=next(iter(found))
    return int(amount) if currency=="KRW" and amount==amount.to_integral_value() else None


def original_matches(msg,item,kind):
    subject=str(msg.get("Subject",""))
    sender={a.lower() for _,a in getaddresses([str(msg.get("From",""))])}
    try:
        t=parsedate_to_datetime(str(msg.get("Date","")))
    except (ValueError,TypeError,IndexError):
        return False
    return (sender=={"css@novogene-amea.com"} and not msg.get("In-Reply-To")
            and subject[:500]==item["subject"] and exact_key(subject)==item["key"]
            and str(msg.get("Message-ID",""))[:300]==item["message_id"]
            and t is not None and t.tzinfo is not None and t==instant(item["date"])
            and (bool(ISSUE.match(subject)) if kind=="ISSUE" else ready(subject) and not ISSUE.match(subject)))


def payload(im,uid,query,max_bytes):
    status,parts=im.uid("FETCH",uid,query)
    if status!="OK":
        return None
    hits=[z for z in parts or [] if isinstance(z,tuple) and len(z)==2
          and isinstance(z[0],bytes) and isinstance(z[1],bytes)]
    if len(hits)!=1:
        return None
    meta,raw=hits[0]
    if not re.search(rb"\bUID\s+"+re.escape(uid.encode("ascii"))+rb"\b",meta,re.I):
        return None
    return raw if len(raw)<=max_bytes else None


def bounded_size(im,uid):
    status,parts=im.uid("FETCH",uid,"(UID RFC822.SIZE)")
    if status!="OK":
        return None
    hits=[]
    for p in parts or []:
        if isinstance(p,bytes) and re.search(rb"\bUID\s+"+re.escape(uid.encode("ascii"))+rb"\b",p,re.I):
            m=re.search(rb"\bRFC822\.SIZE\s+(\d+)\b",p,re.I)
            if m:hits.append(int(m.group(1)))
    return hits[0] if len(hits)==1 and 0<hits[0]<=MAX_BYTES else None


def invoice_amounts(im,item):
    status,parts=im.uid("FETCH",item["uid"],"(UID BODYSTRUCTURE)")
    if status!="OK":
        return None
    raw=b" ".join(imap_bodystructure_chunks(parts))
    if not re.search(rb"\bUID\s+"+re.escape(item["uid"].encode("ascii"))+rb"\b",raw,re.I):
        return None
    records={}
    for name in bodystructure_filenames(raw):
        p=extract(name)
        if not p:
            continue
        ident,_,_,_,amount,_=p
        if not re.fullmatch(r"209126\d{6}",ident) or amount is None or amount<=0:
            return None
        if ident in records and records[ident]!=amount:
            return None
        records[ident]=amount
    return records or None


def inspect(im,pending,issue_only):
    status,_=im.select("INBOX",readonly=True)
    if status!="OK":raise RuntimeError("STATEMENT_RECOVERY_INBOX_SELECT")
    _,uv=im.response("UIDVALIDITY")
    current=uv[0].decode("ascii") if uv and uv[0] else ""
    if not re.fullmatch(r"\d+",current):raise RuntimeError("STATEMENT_RECOVERY_UIDVALIDITY")
    items=[("STATEMENT",r) for r in pending.values()]+[("ISSUE",r) for r in issue_only.values()]
    items.sort(key=lambda v:(v[0]=="ISSUE",instant(v[1]["date"])),reverse=True)
    counts=Counter(); pending_by_month=defaultdict(lambda:{"verified_candidate_count":0,"statement_krw_vat_basis_unknown":0})
    issue_by_month=defaultdict(lambda:{"candidate_invoice_count":0,"candidate_gross_krw":0})
    for kind,item in items[:MAX_ITEMS]:
        if item["uidvalidity"]!=current:
            counts[kind+"_UIDVALIDITY_REVIEW"]+=1;continue
        header=payload(im,item["uid"],"(UID BODY.PEEK[HEADER])",128*1024)
        if header is None:
            counts[kind+"_HEADER_UNAVAILABLE"]+=1;continue
        msg=BytesParser(policy=default).parsebytes(header,headersonly=True)
        if not original_matches(msg,item,kind):
            counts[kind+"_HEADER_IDENTITY_REVIEW"]+=1;continue
        when=instant(item["date"]).astimezone(KST)
        if kind=="ISSUE":
            records=invoice_amounts(im,item)
            if not records:
                counts["ISSUE_FILENAME_AMOUNT_REVIEW"]+=1;continue
            counts["ISSUE_ORIGINAL_FILENAME_AMOUNT_FOUND"]+=1
            m=issue_by_month[when.strftime("%Y-%m")]
            m["candidate_invoice_count"]+=len(records);m["candidate_gross_krw"]+=sum(records.values())
            continue
        size=bounded_size(im,item["uid"])
        if size is None:
            counts["STATEMENT_SIZE_REVIEW"]+=1;continue
        raw=payload(im,item["uid"],"(UID BODY.PEEK[])",size)
        if raw is None or len(raw)!=size:
            counts["STATEMENT_BODY_UNAVAILABLE"]+=1;continue
        msg=BytesParser(policy=default).parsebytes(raw)
        if not original_matches(msg,item,kind):
            counts["STATEMENT_BODY_IDENTITY_REVIEW"]+=1;continue
        amount=statement_total(msg)
        if amount is None:
            counts["STATEMENT_TOTAL_REVIEW"]+=1;continue
        counts["STATEMENT_ORIGINAL_TOTAL_FOUND"]+=1
        month=(when.date()+dt.timedelta(days=5)).strftime("%Y-%m")
        m=pending_by_month[month];m["verified_candidate_count"]+=1;m["statement_krw_vat_basis_unknown"]+=amount
    return {"candidate_groups":len(items),"examined":min(len(items),MAX_ITEMS),"deferred":max(0,len(items)-MAX_ITEMS),
            "results":dict(counts),"statement_candidate_by_due_month":dict(pending_by_month),
            "issue_candidate_by_receipt_month":dict(issue_by_month),"mail_writes":0,"business_writes":0,
            "publication":"NOT_AUTHORIZED_BY_THIS_PROBE"}


def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    from incremental_sync import COLS
    from unified_followup_sync import SRC
    creds=service_account.Credentials.from_service_account_info(json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
                     scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    mail=read_full_source(session,SRC,"CSS Git Ingest",COLS)
    invoice=read_full_source(session,SRC,"CSS Tax Invoice Extract",HEADER)
    pending,issue_only,summary=select_candidates(mail,invoice)
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        out=inspect(im,pending,issue_only)
    print("STATEMENT_RECOVERY_ORIGINAL_AUDIT "+json.dumps({"source":summary,**out},sort_keys=True))


if __name__=="__main__":
    try:main()
    except Exception as e:
        # Exception text may contain source payload. Emit type only.
        print("STATEMENT_RECOVERY_FAILED "+type(e).__name__,file=sys.stderr);sys.exit(1)
