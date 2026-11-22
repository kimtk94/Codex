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
from pathlib import Path
import re
import sys
from decimal import Decimal,ROUND_HALF_UP
from collections import Counter

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

from qq_invoice_parity_audit import load_rows,money
from tax_invoice_extract import (extract,bodystructure_filenames,
                                 imap_bodystructure_chunks,ISSUED,
                                 REPLY_PREFIX,CSS_SENDER)
from invoice_fallback import corroborated_filename

OCT="2026-10"
START="2026-10"
MAX_CANDIDATES=40
EVIDENCE_STATES={"FILENAME_PARSED","SUBJECT_CORROBORATED_FILENAME"}
KST=dt.timezone(dt.timedelta(hours=9))



def verify_backfill_freshness(rows, now=None, max_age_hours=36):
    """Fail closed on missing or stale QQ scan; a green workflow is not source parity."""
    if not rows or "year" not in rows[0] or "status" not in rows[0]:
        raise ValueError("BACKFILL_AUDIT_SCHEMA_MISSING")
    year_rows=[r for r in rows if str(r.get("year", ""))=="2026"]
    if not year_rows:
        raise ValueError("BACKFILL_AUDIT_YEAR_MISSING")
    row=max(year_rows,key=lambda r:str(r.get("last_run_utc") or ""))
    if str(row.get("status", ""))!="SCAN_COMPLETE":
        raise ValueError("BACKFILL_AUDIT_NOT_COMPLETE")
    try:
        stamp=dt.datetime.fromisoformat(
            str(row["last_run_utc"]).replace("Z","+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("NAIVE_TIMESTAMP")
    except (ValueError, KeyError):
        raise ValueError("BACKFILL_AUDIT_TIMESTAMP_INVALID") from None
    current=now if now is not None else dt.datetime.now(dt.timezone.utc)
    age=(current.astimezone(dt.timezone.utc)-
         stamp.astimezone(dt.timezone.utc)).total_seconds()/3600
    if age < -5/60:
        raise ValueError("BACKFILL_AUDIT_CLOCK_SKEW")
    if age>max_age_hours:
        raise ValueError("BACKFILL_AUDIT_STALE")
    return {"status":"SOURCE_FRESH","last_scan_utc":stamp.isoformat(),
            "age_hours":round(max(age,0),2)}


def write_private_safe_report(summary):
    """Allowlisted aggregate-only result for short-lived CI artifact."""
    dest=os.environ.get("INVOICE_AUDIT_SUMMARY_PATH","").strip()
    if not dest:return
    valid={"PASS","NO_NEW_DATA","HOLD","SOURCE_UNAVAILABLE","BLOCK"}
    if summary.get("status") not in valid:
        raise ValueError("INVALID_INVOICE_AUDIT_STATUS")
    payload={k:v for k,v in summary.items()
             if k in {"status","audit_at_utc","backfill","qq_only","qq_only_excluded",
                      "qq_only_verified","qq_only_review","extract_overlap",
                      "extract_metadata_hold","extract_eligible","extract_verified",
                      "extract_excluded","extract_review","metadata_hold_reasons",
                      "source_writes","revenue_writes","error_type"}}
    Path(dest).write_text(json.dumps(payload,sort_keys=True,ensure_ascii=False)+"\n",
                          encoding="utf-8")


def numeric(v):
    s=str(v or "").strip()
    if not re.fullmatch(r"\d+",s):raise ValueError("BAD_ORIGINAL_INVOICE_AMOUNT")
    x=int(s)
    if x<=0:raise ValueError("BAD_ORIGINAL_INVOICE_AMOUNT")
    return x


def net(v):
    return int((Decimal(v)*Decimal(10)/Decimal(11)).quantize(
        Decimal("1"),rounding=ROUND_HALF_UP))


def identify_missing(backfill,extracted,canonical=None,start_month=START):
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
    # Legacy CSS and the derived Extract are different projections.
    # Both must be checked before declaring an invoice unmatched.
    if canonical is not None:
        if not canonical or "invoice_number" not in canonical[0]:
            raise ValueError("CANONICAL_INVOICE_SCHEMA_MISSING")
        for row in canonical:
            inv=str(row.get("invoice_number") or "").strip()
            if not inv:continue
            # CSS canonical uses formatted KRW strings; QQ evidence remains strict integer.
            amount=money(row.get("amount_krw"))
            if amount<=0:raise ValueError("INVALID_CANONICAL_INVOICE_AMOUNT")
            if inv in known and known[inv]!=amount:
                raise ValueError("CANONICAL_EXTRACT_INVOICE_AMOUNT_CONFLICT")
            known[inv]=amount
    new={}
    for row in backfill:
        month=str(row.get("issued_month") or "").strip()
        if not month.startswith('2026-') or month<start_month:continue
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


def select_extracted_original_candidates(backfill, extracted, canonical):
    """Read-only source triage; an Extract row alone never authorizes a financial write."""
    if not backfill or "invoice_number" not in backfill[0]:
        raise ValueError("QQ_BACKFILL_SCHEMA_MISSING")
    if not extracted or "invoice_number" not in extracted[0]:
        raise ValueError("INVOICE_EXTRACT_SCHEMA_MISSING")
    if not canonical or "invoice_number" not in canonical[0]:
        raise ValueError("CANONICAL_INVOICE_SCHEMA_MISSING")
    canonical_ids={str(x.get("invoice_number") or "").strip()
                   for x in canonical if x.get("invoice_number")}
    qq={}
    for row in backfill:
        month=str(row.get("issued_month") or "").strip()
        if not month.startswith("2026-"):continue
        inv=str(row.get("invoice_number") or "").strip()
        if not re.fullmatch(r"209126\d{6}",inv):continue
        if inv in qq:raise ValueError("QQ_INVOICE_DUPLICATE_REQUIRES_REVIEW")
        qq[inv]=row
    extract_map={}
    for row in extracted:
        inv=str(row.get("invoice_number") or "").strip()
        if inv not in qq or inv in canonical_ids:continue
        if inv in extract_map:raise ValueError("EXTRACT_INVOICE_DUPLICATE_REQUIRES_REVIEW")
        extract_map[inv]=row
    accepted={}; holds=Counter(); held_rows=0
    for inv,derived in extract_map.items():
        source=qq[inv]
        reasons=[]
        if str(derived.get("validation_status") or "") != "FILENAME_PARSED":
            reasons.append("EXTRACT_PROVENANCE_UNVERIFIED")
        state=str(source.get("evidence") or "")
        if state not in EVIDENCE_STATES:reasons.append("QQ_PROVENANCE_UNVERIFIED")
        folder=str(source.get("imap_folder") or "").upper()
        if folder!="INBOX":reasons.append("QQ_FOLDER_NOT_INBOX")
        uid=str(source.get("imap_uid") or "").strip()
        if not uid.isdigit() or int(uid)<=0:reasons.append("QQ_UID_INVALID")
        try:
            amount=numeric(source.get("amount_krw"))
            derived_amount=numeric(derived.get("amount_krw"))
            if amount!=derived_amount:reasons.append("EXTRACT_AMOUNT_MISMATCH")
        except ValueError:
            amount=None
            reasons.append("SOURCE_AMOUNT_UNVERIFIED")
        identity=(
            ("AMEA",source.get("amea_project_id"),derived.get("project_id")),
            ("CONTRACT",source.get("h_project_id"),derived.get("h_project_number")),
            ("PO",source.get("po_reference"),derived.get("po_reference")),
            ("UID",source.get("imap_uid"),derived.get("imap_uid")),
        )
        for label,left,right in identity:
            left=str(left or "").strip().upper()
            right=str(right or "").strip().upper()
            if not left or not right:
                reasons.append(label+"_MISSING")
            elif left!=right:
                reasons.append(label+"_MISMATCH")
        if reasons:
            held_rows+=1
            holds.update(set(reasons))
            continue
        accepted[inv]=(str(source["issued_month"]),amount,
                       str(source["amea_project_id"]).strip().upper(),state,uid,
                       str(source["h_project_id"]).strip().upper(),
                       str(source["po_reference"]).strip().upper())
    return accepted,held_rows,dict(sorted(holds.items())),len(extract_map)


def header_payload(parts):
    chunks=[part[1] for part in parts or []
            if isinstance(part,tuple) and isinstance(part[1],bytes)]
    if not chunks:raise ValueError("IMAP_ORIGINAL_HEADER_PAYLOAD_MISSING")
    return BytesParser(policy=default).parsebytes(chunks[0],headersonly=True)


def assert_official_notice(msg):
    """Fail on non-CSS sender, replies and non-original notice before MIME fetch."""
    sender=parseaddr(str(msg.get("From") or ""))[1].casefold()
    subject=str(msg.get("Subject") or "").strip()
    known_sender=sender==CSS_SENDER
    known_domain=sender.endswith(("@novogene.com","@novogene-amea.com",
                                  "@novogene.cn"))
    official_subject=bool(ISSUED.match(subject))
    keyword_subject=("invoice issued" in subject.lower()
                     and "statement confirmed" in subject.lower())
    is_reply=bool(REPLY_PREFIX.match(subject))
    reply_header=bool(str(msg.get("In-Reply-To") or "").strip())
    if not (known_sender and official_subject and not is_reply
            and not reply_header):
        # Expose ONLY bounded boolean classification, never headers, sender
        # email, addresses or customer information in CI logs.
        raise ValueError("ORIGINAL_TAX_INVOICE_EMAIL_IDENTITY_UNVERIFIED"+
                         ":sender_css="+str(known_sender).lower()+
                         ":sender_novogene_domain="+str(known_domain).lower()+
                         ":official_notice="+str(official_subject).lower()+
                         ":invoice_terms="+str(keyword_subject).lower()+
                         ":subject_reply="+str(is_reply).lower()+
                         ":reply_header="+str(reply_header).lower())


def original_proof(msg,attachment_names,invoice,expected):
    month,amount,amea,state,uid=expected[:5]
    required_h,required_po=(expected[5],expected[6]) if len(expected)==7 else (None,None)
    assert_official_notice(msg)
    subject=str(msg.get("Subject") or "").strip()
    matches=[]
    for filename in attachment_names:
        x=extract(filename)
        if not x:
            x=corroborated_filename(filename,subject)
        if not x:continue
        parsed_invoice,h,po,project,value,parsed_state=x
        if parsed_invoice==invoice:
            matches.append((project.upper(),value,parsed_state,
                            str(h or '').upper(),str(po or '').upper()))
    if not matches:raise ValueError("MISSING_INVOICE_ORIGINAL_FILENAME_NOT_FOUND")
    if any(project!=amea or value!=amount
           for project,value,parsed_state,_,_ in matches):
        raise ValueError("MISSING_INVOICE_AMOUNTS_OR_AMEA_CONFLICT")
    if required_h and any(h!=required_h for _,_,_,h,_ in matches):
        raise ValueError("ORIGINAL_CONTRACT_MISMATCH")
    if required_po and any(po!=required_po for _,_,_,_,po in matches):
        raise ValueError("ORIGINAL_PO_MISMATCH")
    if state=="FILENAME_PARSED" and not any(
            marker=="FILENAME_PARSED" for _,_,marker,_,_ in matches):
        raise ValueError("MISSING_INVOICE_STRICT_FILENAME_DOWNGRADED")
    if state=="SUBJECT_CORROBORATED_FILENAME" and not any(
            marker in EVIDENCE_STATES for _,_,marker,_,_ in matches):
        raise ValueError("MISSING_INVOICE_FALLBACK_NOT_CORROBORATED")
    return {"month":month,"amount":amount,"net":net(amount),
            "kind":state,"sender_verified":True}


def audit_with_original_imap(missing,imap_factory=imaplib.IMAP4_SSL):
    verified={};blocked={};excluded={}
    if not missing:return verified,blocked,excluded
    user=os.environ["CSS_QQ_MAIL_ADDRESS"]
    pw=os.environ["CSS_QQ_MAIL_AUTH_CODE"]
    with imap_factory("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(user,pw)
        status,_=im.select("INBOX",readonly=True)
        if status!="OK":raise ValueError("INBOX_READ_ONLY_UNAVAILABLE")
        for inv,expected in sorted(missing.items()):
            uid=expected[4]
            try:
                status,head=im.uid("FETCH",uid,
                                   "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT IN-REPLY-TO)])")
                if status!="OK":raise ValueError("HEADER_FETCH_FAILED")
                msg=header_payload(head)
                assert_official_notice(msg)
                status,parts=im.uid("FETCH",uid,"(BODYSTRUCTURE)")
                if status!="OK":raise ValueError("BODYSTRUCTURE_FETCH_FAILED")
                names=[]
                for x in imap_bodystructure_chunks(parts):
                    names.extend(bodystructure_filenames(x))
                if not names:raise ValueError("NO_TAX_INVOICE_ATTACHMENT_FILENAME")
                verified[inv]=original_proof(msg,names,inv,expected)
            except (ValueError,TypeError) as exc:
                error=type(exc).__name__+":"+str(exc)
                if (isinstance(exc,ValueError) and
                        str(exc).startswith(
                            "ORIGINAL_TAX_INVOICE_EMAIL_IDENTITY_UNVERIFIED")):
                    # Original email is categorically NOT the official CSS
                    # issued-notice sender/subject. A reply is also excluded,
                    # not a collectible Revenue gap. Preserve reasons.
                    excluded[inv]=error
                else:
                    blocked[inv]=error
        im.logout()
    return verified,blocked,excluded


def main():
    creds=service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    source_health=verify_backfill_freshness(load_rows(session,"QQ Backfill Audit",100))
    qq=load_rows(session,"QQ 2026 Invoice Backfill",4000)
    extracted=load_rows(session,"CSS Tax Invoice Extract",1000)
    canonical=load_rows(session,"CSS Tax Invoice List",2000)
    missing=identify_missing(qq,extracted,canonical=canonical,start_month="2026-01")
    print("MAIL_ONLY_MISSING_START source=QQ_2026_BACKFILL"+
          " absent_from=CSS_TAX_INVOICE_EXTRACT_AND_LIST"+
          " count="+str(len(missing))+
          " excluded=MANUAL_ERP_ETAX_FORECAST_PENDING",flush=True)
    verified,blocked,excluded=audit_with_original_imap(missing)
    eligible,meta_held,meta_reasons,extract_overlap=select_extracted_original_candidates(
        qq,extracted,canonical)
    if len(eligible)>MAX_CANDIDATES:
        raise ValueError("DERIVED_PROOF_SCOPE_TOO_LARGE")
    original_derived,blocked_derived,excluded_derived=audit_with_original_imap(eligible)
    print("DERIVED_EXTRACT_ORIGINAL_EVIDENCE"+
          " overlapped="+str(extract_overlap)+
          " eligible="+str(len(eligible))+
          " metadata_hold="+str(meta_held)+
          " original_verified="+str(len(original_derived))+
          " original_excluded="+str(len(excluded_derived))+
          " original_review="+str(len(blocked_derived))+
          " hold_reasons="+json.dumps(meta_reasons,sort_keys=True)+
          " source_writes=0 revenue_writes=0",flush=True)
    # GitHub CI is not a customer data destination: no invoice numbers,
    # monetary values, customer identifiers or raw mailbox headers in logs.
    by=Counter(detail["month"] for detail in verified.values())
    for month,count in sorted(by.items()):
        print("MAIL_ONLY_VERIFIED_MISSING_MONTH month="+month+
              " count="+str(count),flush=True)
    print("MAIL_ONLY_PRIVATE_EVIDENCE_REDACTED"+
          " excluded_not_official="+str(len(excluded))+
          " hold_needs_review="+str(len(blocked)),flush=True)
    print("MAIL_ONLY_AUDIT_RESULT candidates="+str(len(missing))+
          " original_verified_missing="+str(len(verified))+
          " nonofficial_excluded="+str(len(excluded))+
          " review="+str(len(blocked))+
          " source_writes=0 revenue_writes=0",flush=True)
    if len(verified)+len(blocked)+len(excluded)!=len(missing):
        raise ValueError("MAIL_ONLY_MISSING_SOURCE_NOT_FULLY_CLASSIFIED")
    status=("HOLD" if (meta_held or blocked_derived or excluded_derived
                       or original_derived or blocked or verified) else
            "NO_NEW_DATA" if not missing and not extract_overlap else "PASS")
    write_private_safe_report({
        "status":status,
        "audit_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "backfill":source_health,
        "qq_only":len(missing),
        "qq_only_excluded":len(excluded),
        "qq_only_verified":len(verified),
        "qq_only_review":len(blocked),
        "extract_overlap":extract_overlap,
        "extract_metadata_hold":meta_held,
        "extract_eligible":len(eligible),
        "extract_verified":len(original_derived),
        "extract_excluded":len(excluded_derived),
        "extract_review":len(blocked_derived),
        "metadata_hold_reasons":meta_reasons,
        "source_writes":0,"revenue_writes":0
    })
    print("MAIL_ONLY_AGGREGATE_STATUS="+status+" SOURCE="+source_health["status"],flush=True)
    # Independent original proof is necessary, but still never sufficient for
    # automatic promotion to canonical Invoice/Revenue/Payment.
    if meta_held or blocked_derived or excluded_derived or original_derived:
        raise ValueError("DERIVED_EXTRACT_ORIGINAL_REVIEW_REQUIRED")
    if blocked:
        raise ValueError("MAIL_ONLY_ORIGINAL_CONFIRMATION_INCOMPLETE")
    if verified:
        # Verified original CSS source but missing from monthly input:
        # hold until source ingestion has promoted the document.
        raise ValueError("MAIL_ONLY_REVENUE_SOURCE_COVERAGE_GAP_"+
                         str(len(verified)))
    print("MAIL_ONLY_SOURCE_POLICY_PASS every_extra_historical_mail="+
          ("EXCLUDED_NOT_ORIGINAL" if missing else "NO_GAP")+
          " genuine_official_missing=0"+
          " manual_ERP_eTax_invoice_allowed=0",flush=True)


if __name__=="__main__":
    try:main()
    except Exception as exc:
        # If failure occurred before a complete report, record BLOCK without
        # publishing exception payloads from remote services or mail headers.
        dest=os.environ.get("INVOICE_AUDIT_SUMMARY_PATH","").strip()
        if not dest or not Path(dest).exists():
            write_private_safe_report({
                "status":"SOURCE_UNAVAILABLE" if isinstance(exc,(OSError,KeyError))
                else "BLOCK",
                "audit_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                "error_type":type(exc).__name__,
                "source_writes":0,"revenue_writes":0
            })
        print("MAIL_ONLY_AUDIT_NOT_COMPLETE="+type(exc).__name__,
              file=sys.stderr)
        sys.exit(1)
