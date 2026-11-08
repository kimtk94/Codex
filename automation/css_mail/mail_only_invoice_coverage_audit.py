#!/usr/bin/env python3
"""Audit only real QQ original CSS TAX INVOICE emails missing from Revenue feed.

Never use ERP/eTax manual invoices, QQ Sent, pending, forecasting, other-sales
mailboxes, or inferred project/quote matches. No mailbox or Sheet writes.
If an original filename/subject/amount cannot be fully checked, leave it HOLD.
"""
import datetime as dt
import email
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr
import imaplib
import json
import os
import re
import sys
from decimal import Decimal,ROUND_HALF_UP
from collections import Counter

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

from qq_invoice_parity_audit import load_rows
from tax_invoice_extract import (extract,bodystructure_filenames,
                                 imap_bodystructure_chunks,ISSUED,
                                 REPLY_PREFIX,CSS_SENDER)
from invoice_fallback import corroborated_filename

OCT="2026-10"
START="2026-10"
MAX_CANDIDATES=40
EVIDENCE_STATES={"FILENAME_PARSED","SUBJECT_CORROBORATED_FILENAME"}
KST=dt.timezone(dt.timedelta(hours=9))


def numeric(v):
    s=str(v or "").strip()
    if not re.fullmatch(r"\d+",s):raise ValueError("BAD_ORIGINAL_INVOICE_AMOUNT")
    x=int(s)
    if x<=0:raise ValueError("BAD_ORIGINAL_INVOICE_AMOUNT")
    return x


def net(v):
    return int((Decimal(v)*Decimal(10)/Decimal(11)).quantize(
        Decimal("1"),rounding=ROUND_HALF_UP))


def identify_missing(backfill,extracted):
    if not backfill or "invoice_number" not in backfill[0]:
        raise ValueError("QQ_BACKFILL_SCHEMA_MISSING")
    if not extracted or "invoice_number" not in extracted[0]:
        raise ValueError("INVOICE_EXTRACT_SCHEMA_MISSING")
    known={}
    for row in extracted:
        inv=str(row.get("invoice_number") or "").strip()
        if not inv:continue
        amount=numeric(row.get("amount_krw"))
        if inv in known and known[inv]!=amount:
            raise ValueError("EXTRACT_INVOICE_CONFLICT")
        known[inv]=amount
    new={}
    for row in backfill:
        month=str(row.get("issued_month") or "").strip()
        if month<START:continue
        inv=str(row.get("invoice_number") or "").strip()
        if not re.fullmatch(r"209126\d{6}",inv):continue
        state=str(row.get("evidence") or "").strip()
        if state not in EVIDENCE_STATES:continue
        amount=numeric(row.get("amount_krw"))
        if inv in known:
            if known[inv]!=amount:raise ValueError("BACKFILL_EXTRACT_AMOUNT_CONFLICT")
            continue
        if not str(row.get("imap_folder") or "").upper()=="INBOX":
            raise ValueError("MISSING_MAIL_NOT_ORIGINAL_INBOX")
        uid=str(row.get("imap_uid") or "").strip()
        if not uid.isdigit() or not uid or int(uid)<=0:
            raise ValueError("MISSING_MAIL_UID_INVALID")
        expected=(month,amount,str(row.get("amea_project_id") or "").upper(),state,uid)
        if inv in new and new[inv]!=expected:
            raise ValueError("BACKFILL_DUPLICATE_SOURCE_CONFLICT")
        new[inv]=expected
    if len(new)>MAX_CANDIDATES:
        raise ValueError("MAIL_MISSING_SCOPE_TOO_LARGE")
    return new


def header_payload(parts):
    chunks=[part[1] for part in parts or []
            if isinstance(part,tuple) and isinstance(part[1],bytes)]
    if not chunks:raise ValueError("IMAP_ORIGINAL_HEADER_PAYLOAD_MISSING")
    return BytesParser(policy=default).parsebytes(chunks[0],headersonly=True)


def original_proof(msg,attachment_names,invoice,expected):
    month,amount,amea,state,uid=expected
    sender=parseaddr(str(msg.get("From") or ""))[1].casefold()
    subject=str(msg.get("Subject") or "").strip()
    if (sender!=CSS_SENDER or
            not ISSUED.match(subject) or
            REPLY_PREFIX.match(subject) or
            str(msg.get("In-Reply-To") or "").strip()):
        raise ValueError("ORIGINAL_TAX_INVOICE_EMAIL_IDENTITY_UNVERIFIED")
    matches=[]
    for filename in attachment_names:
        x=extract(filename)
        if not x:
            x=corroborated_filename(filename,subject)
        if not x:continue
        parsed_invoice,h,po,project,value,parsed_state=x
        if parsed_invoice==invoice:
            matches.append((project.upper(),value,parsed_state))
    if not matches:raise ValueError("MISSING_INVOICE_ORIGINAL_FILENAME_NOT_FOUND")
    if any(project!=amea or value!=amount
           for project,value,parsed_state in matches):
        raise ValueError("MISSING_INVOICE_AMOUNTS_OR_AMEA_CONFLICT")
    if state=="FILENAME_PARSED" and not any(
            marker=="FILENAME_PARSED" for _,_,marker in matches):
        raise ValueError("MISSING_INVOICE_STRICT_FILENAME_DOWNGRADED")
    if state=="SUBJECT_CORROBORATED_FILENAME" and not any(
            marker in EVIDENCE_STATES for _,_,marker in matches):
        raise ValueError("MISSING_INVOICE_FALLBACK_NOT_CORROBORATED")
    return {"month":month,"amount":amount,"net":net(amount),
            "kind":state,"sender_verified":True}


def audit_with_original_imap(missing,imap_factory=imaplib.IMAP4_SSL):
    verified={};blocked={}
    if not missing:return verified,blocked
    user=os.environ["CSS_QQ_MAIL_ADDRESS"]
    pw=os.environ["CSS_QQ_MAIL_AUTH_CODE"]
    with imap_factory("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(user,pw)
        status,_=im.select("INBOX",readonly=True)
        if status!="OK":raise ValueError("INBOX_READ_ONLY_UNAVAILABLE")
        for inv,expected in sorted(missing.items()):
            uid=expected[-1]
            try:
                status,head=im.uid("FETCH",uid,
                                   "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT IN-REPLY-TO)])")
                if status!="OK":raise ValueError("HEADER_FETCH_FAILED")
                msg=header_payload(head)
                status,parts=im.uid("FETCH",uid,"(BODYSTRUCTURE)")
                if status!="OK":raise ValueError("BODYSTRUCTURE_FETCH_FAILED")
                names=[]
                for x in imap_bodystructure_chunks(parts):
                    names.extend(bodystructure_filenames(x))
                if not names:raise ValueError("NO_TAX_INVOICE_ATTACHMENT_FILENAME")
                verified[inv]=original_proof(msg,names,inv,expected)
            except (ValueError,TypeError) as exc:
                blocked[inv]=type(exc).__name__+":"+str(exc)
        im.logout()
    return verified,blocked


def main():
    creds=service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    qq=load_rows(session,"QQ 2026 Invoice Backfill",4000)
    extracted=load_rows(session,"CSS Tax Invoice Extract",1000)
    missing=identify_missing(qq,extracted)
    print("MAIL_ONLY_MISSING_START source=QQ_2026_BACKFILL"+
          " absent_from=CSS_TAX_INVOICE_EXTRACT"+
          " count="+str(len(missing))+
          " excluded=MANUAL_ERP_ETAX_FORECAST_PENDING",flush=True)
    verified,blocked=audit_with_original_imap(missing)
    for inv,detail in sorted(verified.items()):
        print("MAIL_ONLY_ORIGINAL_PROOF invoice="+inv+
              " month="+detail["month"]+
              " gross_krw="+str(detail["amount"])+
              " net_krw="+str(detail["net"])+
              " filename_evidence="+detail["kind"]+
              " css_sender_and_original_notice=PASS",flush=True)
    for inv,reason in sorted(blocked.items()):
        print("MAIL_ONLY_ORIGINAL_HOLD invoice="+inv+" reason="+reason,flush=True)
    by={}
    for inv,detail in verified.items():
        rec=by.setdefault(detail["month"],[0,0,0])
        rec[0]+=1;rec[1]+=detail["amount"];rec[2]+=detail["net"]
    for month,info in sorted(by.items()):
        print("MAIL_ONLY_VERIFIED_MISSING_MONTH month="+month+
              " count="+str(info[0])+" gross_krw="+str(info[1])+
              " net_krw="+str(info[2]),flush=True)
    print("MAIL_ONLY_AUDIT_RESULT missing="+str(len(missing))+
          " original_verified="+str(len(verified))+
          " review="+str(len(blocked))+
          " source_writes=0 revenue_writes=0",flush=True)
    if blocked:
        raise ValueError("MAIL_ONLY_ORIGINAL_CONFIRMATION_INCOMPLETE")
    if missing:
        # Not silently mark a successful full Revenue sync when verified
        # original CSS mail exists but is absent from the monthly source.
        raise ValueError("MAIL_ONLY_REVENUE_SOURCE_COVERAGE_GAP_"+
                         str(len(verified)))


if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("MAIL_ONLY_AUDIT_NOT_COMPLETE="+type(exc).__name__+":"+
              str(exc),file=sys.stderr)
        sys.exit(1)
