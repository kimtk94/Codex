#!/usr/bin/env python3
"""Verify pending Statement amounts from original QQ IMAP messages, read-only.

No email mutation or attachment download. Never infer a Pending amount from
project forecast, quotation, or a different J installment.
"""
import datetime as dt
import imaplib
import os
import re
import sys
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses

import incremental_sync as css
from unified_followup_sync import SRC, get, put
from pending_statement_uid_amounts import amounts

TAB = "CSS Statement Amount Extract"
HEAD = ["statement_key","project_x","statement_no","amount_krw","currency",
        "notice_at","imap_uid","uidvalidity","validation_status",
        "verified_at_utc","subject"]
SJ = re.compile(r"(J\d{3})-(X\d+SC\d+-Z\d+)",re.I)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
CSS_FROM = "css@novogene-amea.com"
VALID_INVOICES = {"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}

def cell(r, i):
    return str(r[i]) if i < len(r) and r[i] is not None else ""

def notice(subject):
    low = subject.lower()
    return "statement" in low and (
        "ready for confirmation" in low or "revised statement" in low
    )

def candidates(mail, invoice):
    issued = set()
    for r in invoice[1:]:
        if cell(r,10) not in VALID_INVOICES: continue
        m = SJ.search(cell(r,6))
        if m: issued.add(m.group(1).upper()+"-"+m.group(2).upper())
    result = {}
    for r in mail[1:]:
        if len(r)<16: continue  # Q (In-Reply-To) is omitted for original messages
        if cell(r,3).upper() != "INBOX" or cell(r,6).lower() != CSS_FROM: continue
        if cell(r,15) != "INBOUND" or cell(r,16).strip(): continue
        subject = cell(r,9)
        if REPLY.match(subject) or not notice(subject):continue
        m = SJ.search(subject)
        if not m:continue
        j,x = m.group(1).upper(),m.group(2).upper()
        key=j+"-"+x
        if key in issued:continue
        # Most recent revised statement supersedes earlier original notices.
        if key not in result or (cell(r,5),cell(r,2)) > (
            result[key]["date"],result[key]["uid"]):
            result[key] = {"key":key,"x":x,"j":j,"date":cell(r,5),
                           "uid":cell(r,2),"uidvalidity":cell(r,4),
                           "subject":subject}
    return result

def original_identity(msg, key):
    subject=str(msg.get("Subject",""))
    senders={address.lower() for _,address in getaddresses([str(msg.get("From",""))])}
    return (
        CSS_FROM in senders and
        bool(SJ.search(subject)) and
        key in subject.upper() and
        notice(subject) and
        not REPLY.match(subject) and
        not msg.get("In-Reply-To")
    )

def row_for(item, amount="", status="NOT_CHECKED"):
    return [item["key"],item["x"],item["j"],amount,"KRW" if amount!="" else "",
            item["date"],item["uid"],item["uidvalidity"],status,
            dt.datetime.now(dt.timezone.utc).isoformat(),item["subject"]]

def sync_verified_pending(session, statement_rows, invoice_rows):
    """Reconcile verified QQ J+X installments: pending -> invoice, once only."""
    from unified_followup_sync import DST
    from tax_invoice_extract import extract
    ledger_tab = "CSS Batch Statement Ledger"
    ledger = get(session, DST, ledger_tab, "A1:O200")
    if not ledger or cell(ledger[0], 0) != "AMEA" or cell(ledger[0], 14) != "Statement ID":
        raise RuntimeError("Unexpected BI pending ledger schema")
    existing = {}
    for row_number, r in enumerate(ledger[1:], 2):
        key = cell(r, 14).strip().upper()
        if key:
            if key in existing: raise RuntimeError("Duplicate Statement ID in ledger: " + key)
            existing[key] = (row_number, r)

    # Invoice recognition requires an original, non-reply notice and a matching
    # invoice number and KRW amount in the attachment filename.
    invoices = {}
    for r in invoice_rows[1:]:
        if cell(r, 10) not in VALID_INVOICES: continue
        subject, filename = cell(r, 6), cell(r, 5)
        if REPLY.match(subject) or not re.match(
                r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",
                subject, re.I):
            continue
        m = SJ.search(subject)
        if not m: continue
        parsed = extract(filename)
        number = cell(r, 0)
        try: amt = int(cell(r, 1))
        except ValueError: continue
        if not parsed or parsed[0] != number or parsed[4] != amt or amt <= 0:
            raise RuntimeError("Invoice filename mismatch: " + number)
        key = m.group(1).upper() + "-" + m.group(2).upper()
        new = (number, amt, cell(r, 7), cell(r, 2))
        entries = invoices.setdefault(key, {})
        if number in entries and entries[number] != new:
            raise RuntimeError("Conflicting duplicate invoice number: " + number)
        entries[number] = new

    # Transition existing pending entries when a matching Tax Invoice arrives.
    # Never create additional Actual revenue here; Revenue Lifecycle owns that.
    transitioned = 0
    for key, (row_number, old) in existing.items():
        if key not in invoices: continue
        matches = list(invoices[key].values())
        if any(amea and amea.upper() != cell(old, 0).upper() for _, _, _, amea in matches):
            raise RuntimeError("Invoice AMEA mismatch: " + key)
        amount_total = sum(amt for _, amt, _, _ in matches)
        old_amount = cell(old, 5)
        try: old_amount = int(old_amount) if old_amount else None
        except ValueError: raise RuntimeError("Invalid Statement amount: " + key)
        # A split invoice may be partial. Keep it out of automatic full-match
        # reconciliation unless the verified J total equals the invoice sum.
        if old_amount is None or old_amount != amount_total:
            numbers = " | ".join(sorted(n for n, _, _, _ in matches))
            if cell(old, 7) and cell(old, 7) != numbers:
                raise RuntimeError("Invoice number changed for " + key)
            issued_at = max(date for _, _, date, _ in matches)
            # Original issuance exists, but the balance cannot be inferred.
            # Exclude the whole Statement from Pending and flag allocation.
            put(session, DST, ledger_tab, "G" + str(row_number),
                [["STATEMENT_INVOICE_ALLOCATION_REVIEW", numbers, amount_total, issued_at,
                  "J_INSTALLMENT_PARTIAL_OR_CONFLICT_REVIEW",
                  "INVOICE_ACTUAL_ONLY_REMAINING_BALANCE_UNVERIFIED",
                  "Original invoice filenames verified; amount allocation differs for " + key,
                  "Review Statement " + str(old_amount) + " vs Invoice " + str(amount_total)
                  + "; exclude from Pending until balance evidenced"]], "RAW")
            print("STATEMENT_INVOICE_ALLOCATION_REVIEW " + key, flush=True)
            transitioned += 1
            continue
        numbers = " | ".join(sorted(n for n, _, _, _ in matches))
        if cell(old, 7) and cell(old, 7) != numbers:
            raise RuntimeError("Invoice number changed for " + key)
        issued_at = max(date for _, _, date, _ in matches)
        put(session, DST, ledger_tab, "G" + str(row_number),
            [["STATEMENT_INVOICED", numbers, amount_total, issued_at,
              "J_INSTALLMENT_INVOICE_MATCH", "INVOICE_ONLY_NO_ADDITIONAL_REVENUE",
              "Original invoice subjects+filenames verified; " + key,
              "Actual by distinct invoice number; remove Statement from Pending"]], "RAW")
        transitioned += 1

    # Only original-message verified, non-invoiced statements can be Pending.
    updated = 0
    for r in statement_rows[1:]:
        key = cell(r, 0).strip().upper()
        if not SJ.fullmatch(key) or cell(r, 8) != "AMOUNT_VERIFIED" or cell(r, 4) != "KRW":
            continue
        if key in invoices: continue
        try: amount = int(cell(r, 3))
        except ValueError: continue
        if amount <= 0: continue
        subject = cell(r, 10)
        amea = re.search(r"AMEA\d{7,}", subject, re.I)
        contract = re.search(r"H\d+SC\d+", subject, re.I)
        x = cell(r, 1)
        if not amea or not contract or not x or key != cell(r, 2).upper() + "-" + x.upper():
            continue
        source = ("QQ original IMAP UID " + cell(r, 6) + "; UIDVALIDITY "
                  + cell(r, 7) + "; AMOUNT_VERIFIED " + cell(r, 9))
        if key in existing:
            row_num, old = existing[key]
            if cell(old, 0).upper() != amea.group(0).upper() or cell(old, 2).upper() != x.upper():
                raise RuntimeError("Pending ledger identity conflict: " + key)
            if cell(old, 7) or cell(old, 8): continue
            if cell(old, 5) and int(float(cell(old, 5))) != amount:
                raise RuntimeError("Statement amount changed; manual review: " + key)
            put(session, DST, ledger_tab, "F" + str(row_num),
                [[amount, "STATEMENT_ORIGINAL_VERIFIED_PENDING"]], "RAW")
            put(session, DST, ledger_tab, "K" + str(row_num),
                [["J_INSTALLMENT_VERIFIED_UNISSUED", "PENDING_VERIFIED_NOT_ACTUAL",
                  source, "Await original Tax Invoice; deduplicate by Statement ID"]], "RAW")
        else:
            row_num = max(len(ledger) + 1, 2)
            if row_num > 200: raise RuntimeError("Pending ledger is full")
            item = [amea.group(0).upper(), contract.group(0).upper(), x, "",
                    cell(r, 5), amount, "STATEMENT_ORIGINAL_VERIFIED_PENDING",
                    "", "", "", "J_INSTALLMENT_VERIFIED_UNISSUED",
                    "PENDING_VERIFIED_NOT_ACTUAL", source,
                    "Await original Tax Invoice; deduplicate by Statement ID", key]
            put(session, DST, ledger_tab, "A" + str(row_num), [item], "RAW")
            ledger.append(item)
            existing[key] = (row_num, item)
        updated += 1
    print("STATEMENT_LEDGER_RECONCILE issued_transitioned=" + str(transitioned)
          + " verified_pending_updated=" + str(updated), flush=True)


def main():
    session=css.authorize()
    mail=get(session,SRC,"CSS Git Ingest","A1:R10000")
    invoices=get(session,SRC,"CSS Tax Invoice Extract","A1:L10000")
    previous=get(session,SRC,TAB,"A1:K2000")
    if not mail or cell(mail[0],0)!="ingest_key":
        raise RuntimeError("Unexpected QQ mail staging schema")
    if not invoices or cell(invoices[0],0)!="invoice_number":
        raise RuntimeError("Unexpected QQ invoice schema")
    if not previous or previous[0]!=HEAD:
        raise RuntimeError("Unexpected Statement amount schema")
    wanted=candidates(mail,invoices)
    known={cell(r,0):r for r in previous[1:] if cell(r,0)}
    # Only retain the latest verified evidence for a given Statement key.
    queue=[v for v in wanted.values() if
        v["key"] not in known or cell(known[v["key"]],6)!=v["uid"] or
        cell(known[v["key"]],8)!="AMOUNT_VERIFIED"]
    queue.sort(key=lambda x:x["date"],reverse=True)
    limit=min(max(int(os.getenv("CSS_STATEMENT_AMOUNT_BATCH","40")),1),100)
    selected=queue[:limit]
    if selected:
        with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
            im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],
                     os.environ["CSS_QQ_MAIL_AUTH_CODE"])
            response,_=im.select("INBOX",readonly=True)
            if response!="OK": raise RuntimeError("QQ INBOX SELECT failed")
            _,uv=im.response("UIDVALIDITY")
            current=(uv[0] or b"").decode() if uv else ""
            if not current: raise RuntimeError("QQ UIDVALIDITY missing")
            for item in selected:
                if item["uidvalidity"]!=current:
                    known[item["key"]]=row_for(item,status="UIDVALIDITY_MISMATCH")
                    continue
                try:
                    status,data=im.uid("FETCH",item["uid"],"(BODY.PEEK[])")
                    payload=next((z[1] for z in data or []
                                  if isinstance(z,tuple) and isinstance(z[1],bytes)),None)
                    if status!="OK" or payload is None:
                        known[item["key"]]=row_for(item,status="MAIL_UNAVAILABLE")
                        continue
                    msg=BytesParser(policy=default).parsebytes(payload)
                    if not original_identity(msg,item["key"]):
                        known[item["key"]]=row_for(item,status="ORIGINAL_IDENTITY_MISMATCH")
                        continue
                    values=amounts(msg)
                    verified=[a for a,unit in values if unit=="KRW"
                              and a>0 and float(a).is_integer()]
                    if len(values)==1 and len(verified)==1:
                        known[item["key"]]=row_for(item,int(verified[0]),"AMOUNT_VERIFIED")
                    elif not values:
                        known[item["key"]]=row_for(item,status="AMOUNT_NOT_FOUND")
                    else:
                        known[item["key"]]=row_for(item,status="AMBIGUOUS_OR_NON_KRW")
                except (imaplib.IMAP4.error,ValueError,TypeError) as exc:
                    print("STATEMENT_UID_RETRY "+item["key"]+" "+type(exc).__name__)
                    known[item["key"]]=row_for(item,status="FETCH_RETRY")
            im.logout()
    out=[HEAD]+[known[k] for k in sorted(known)]
    if len(out)>2000:raise RuntimeError("Statement amount evidence exceeds safe range")
    put(session,SRC,TAB,"A1",out,"RAW")
    check=get(session,SRC,TAB,"A1:K"+str(len(out)))
    if len(check)!=len(out) or check[0]!=HEAD:
        raise RuntimeError("Statement amount post-write verification failed")
    sync_verified_pending(session, out, invoices)
    current=[known[k] for k in wanted if k in known and cell(known[k],6)==wanted[k]["uid"]]
    verified=[r for r in current if cell(r,8)=="AMOUNT_VERIFIED"]
    print("STATEMENT_AMOUNT_EXTRACT_PASS pending_statements="+str(len(wanted))+
          " verified="+str(len(verified))+
          " amount_krw="+str(sum(int(cell(r,3)) for r in verified))+
          " examined="+str(len(selected))+
          " remaining="+str(max(0,len(queue)-len(selected))),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("STATEMENT_AMOUNT_EXTRACT_FAILED "+type(exc).__name__,file=sys.stderr)
        raise
