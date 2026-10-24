#!/usr/bin/env python3
"""Read-only historical QQ TAX INVOICE backfill; never changes source or mail."""
import datetime as dt, imaplib, json, os, re, sys, urllib.parse
from collections import Counter
from email.parser import BytesParser
from email.policy import default
from invoice_fallback import corroborated_filename
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from tax_invoice_extract import extract,bodystructure_filenames

SHEET=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
TAB=os.getenv("BACKFILL_TAB","QQ Historical Invoice Backfill")
CURSOR_TAB=os.getenv("BACKFILL_CURSOR_TAB","QQ Backfill Cursor")
AUDIT_TAB=os.getenv("BACKFILL_AUDIT_TAB","QQ Backfill Audit")
HEAD=["invoice_number","issued_month","amount_krw","amea_project_id","h_project_id","po_reference","imap_folder","imap_uid","filename","evidence","backfill_utc"]
def call(session,method,path,**kw):
    url="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+path
    resp=session.request(method,url,timeout=65,**kw)
    if not resp.ok:raise RuntimeError("SHEETS_"+str(resp.status_code)+" "+resp.text[:220])
    return resp.json() if resp.content else {}
def resolve_uidvalidity(im, folder):
    """Prefer the selected mailbox response, then request STATUS explicitly.

    Exmail may omit an unsolicited UIDVALIDITY response on EXAMINE.
    Refuse to advance persistent cursors when neither source is available.
    """
    status, values = im.response("UIDVALIDITY")
    values = values or []
    for value in values:
        if value:
            raw = value.decode("ascii", "replace") if isinstance(value,bytes) else str(value)
            match = re.search(r"(?:UIDVALIDITY\s+)?([0-9]+)", raw, re.I)
            if match:
                return match.group(1)
    quoted = '"' + folder.replace('"', '') + '"'
    status, values = im.status(quoted, "(UIDVALIDITY)")
    if status == "OK":
        for value in values or []:
            raw = value.decode("ascii","replace") if isinstance(value,bytes) else str(value)
            match = re.search(r"UIDVALIDITY\s+([0-9]+)",raw,re.I)
            if match:
                return match.group(1)
    raise RuntimeError("UIDVALIDITY_UNAVAILABLE_AFTER_STATUS")

def main():
    cred=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    s=AuthorizedSession(cred)
    meta=call(s,"GET","?fields=sheets.properties.title")
    if TAB not in {x["properties"]["title"] for x in meta["sheets"]}:
        call(s,"POST",":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":TAB,"gridProperties":{"rowCount":3000,"columnCount":12,"frozenRowCount":1}}}}]})
    quote=lambda rng:urllib.parse.quote("'"+TAB+"'!"+rng,safe="")
    old=call(s,"GET","/values/"+quote("A1:K10000")).get("values",[])
    if old and old[0]!=HEAD:raise RuntimeError("BACKFILL_HEADER_MISMATCH")
    by_invoice={str(row[0]):row for row in old[1:] if row and row[0]}
    year=int(os.getenv("BACKFILL_YEAR","2025"))
    # Checkpoint per year, folder, and UIDVALIDITY to avoid repeated capped scans.
    tabs={x["properties"]["title"] for x in meta["sheets"]}
    for tab in (CURSOR_TAB,AUDIT_TAB):
        if tab not in tabs:
            call(s,"POST",":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":tab,"gridProperties":{"rowCount":1000,"columnCount":8,"frozenRowCount":1}}}}]})
    def read_tab(tab,area):
        address=urllib.parse.quote("'"+tab+"'!"+area,safe="")
        return call(s,"GET","/values/"+address).get("values",[])
    cursor_header=["year","folder","uidvalidity","last_uid","updated_utc"]
    history=read_tab(CURSOR_TAB,"A1:E1000")
    if history and history[0]!=cursor_header:raise RuntimeError("CURSOR_SCHEMA_MISMATCH")
    cursors={(int(row[0]),row[1]):row[:5] for row in history[1:] if len(row)>=4 and row[0].isdigit() and row[3].isdigit()}
    audit_header=["year","last_run_utc","status","candidates","scanned","filename_candidates","parsed_invoices","new_invoices"]
    audits=read_tab(AUDIT_TAB,"A1:H1000")
    if audits and audits[0]!=audit_header:raise RuntimeError("AUDIT_SCHEMA_MISMATCH")
    audit_by_year={str(row[0]):row for row in audits[1:] if row and row[0]}

    # Verified source evidence is available independently of QQ BODYSTRUCTURE:
    # preserve existing invoices, and skip already-reconciled IMAP UIDs.
    known_uids=set()
    seeded=0
    if year==2026:
        # The canonical legacy invoice ledger covers Jan-Oct 2026; the newer
        # CSS Tax Invoice Extract is only a partial 90-row derived view.
        source=call(s,"GET","/values/"+urllib.parse.quote("'CSS Tax Invoice List'!A1:N1000",safe="")).get("values",[])
        fields=source[0] if source else []
        for values in source[1:]:
            item=dict(zip(fields,values))
            inv=str(item.get("invoice_number","")).strip()
            month=str(item.get("invoice_month","")).strip()
            amount=re.sub(r"[^0-9]","",str(item.get("amount_krw","")))
            if not (inv and month.startswith("2026-") and amount.isdigit()):continue
            source_uid=str(item.get("uid","")).strip()
            folder,_,uid=source_uid.partition(":")
            folder="INBOX" if folder.lower()=="inbox" else folder
            if folder and uid:known_uids.add((folder,uid))
            if inv in by_invoice:
                if len(by_invoice[inv])>2 and str(by_invoice[inv][2])!=amount:
                    raise RuntimeError("VERIFIED_SEED_AMOUNT_CONFLICT")
                continue
            by_invoice[inv]=[inv,month,amount,item.get("project_id",""),
                item.get("h_project_number",""),item.get("po_reference",""),
                folder,uid,item.get("attachment_filename",""),
                "CSS_TAX_INVOICE_LIST_VERIFIED_LEGACY",dt.datetime.now(dt.timezone.utc).isoformat()]
            seeded+=1
        print("QQ_BACKFILL_SEEDED year=2026 verified_existing="+str(seeded)+
              " known_uids="+str(len(known_uids)),flush=True)
        if seeded:
            call(s,"PUT","/values/"+quote("A1")+"?valueInputOption=RAW",
                json={"values":[HEAD]+list(by_invoice.values())})
    scanned=0; matches=0; fetched=0; folders=0; filename_candidates=0; filename_parsed=0
    limit=int(os.getenv("BACKFILL_MAX_MATCHES","2500"))
    unfinished=False; prior_skipped=0; last_by_folder={}
    reject_reasons=Counter()
    fallback_matched=0
    no_uidvalidity_folders=0

    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        status,listing=im.list()
        if status!="OK":raise RuntimeError("IMAP_LIST_FAILED")
        names=[]
        for item in listing or []:
            line=item.decode("utf-8","replace")
            mt=re.search(r' (?:"([^"]+)"|([^ "]+))$',line)
            if mt:names.append(mt.group(1) or mt.group(2))
        # On historical backfills, prioritize INBOX over Sent Messages: source
        # invoice notifications arrive inbound; a capped scan must not spend
        # the entire run on outgoing quotations or statements.
        if year == 2025:
            names.sort(key=lambda name: (0 if name.upper() == "INBOX" else 1, name.lower()))
        for folder in names:
            status,_=im.select('"'+folder.replace('"','')+'"',readonly=True)
            if status!="OK":continue
            folders+=1
            try:
                uidvalidity=resolve_uidvalidity(im, folder)
            except RuntimeError as exc:
                if str(exc)!="UIDVALIDITY_UNAVAILABLE_AFTER_STATUS":raise
                uidvalidity=""
                no_uidvalidity_folders+=1
                unfinished=True
                print("QQ_BACKFILL_WARNING UIDVALIDITY unavailable; cursor disabled for folder="+str(folders),flush=True)
            old_cursor=cursors.get((year,folder))
            checkpoint=int(old_cursor[3]) if old_cursor and old_cursor[2]==uidvalidity else 0
            start=f"01-Jan-{year}";end=f"01-Jan-{year+1}"
            # Broad subject search to find invoice notifications independent of sender.
            found=set()
            for phrase in ('Invoice Issued','TAX INVOICE'):
                status,found_rows=im.uid("SEARCH",None,"SINCE",start,"BEFORE",end,"SUBJECT",'"'+phrase+'"')
                if status=="OK":found.update((found_rows[0] or b"").split())
            matches+=len(found)
            print("QQ_BACKFILL_FOLDER folder_count="+str(folders)+" candidates="+str(len(found)),flush=True)
            eligible=[u for u in sorted(found,key=lambda x:int(x)) if int(u)>checkpoint]
            prior_skipped+=len(found)-len(eligible)
            if scanned>=limit and eligible:unfinished=True
            for uid in eligible:
                if scanned>=limit:
                    unfinished=True
                    break
                if uidvalidity:last_by_folder[folder]=(uidvalidity,int(uid))
                if (folder,uid.decode()) in known_uids:continue
                scanned+=1
                status,parts=im.uid("FETCH",uid,"(BODYSTRUCTURE)")
                if status!="OK":continue
                blocks=[p for p in parts if isinstance(p,bytes)]
                blocks +=[p[0] for p in parts if isinstance(p,tuple) and isinstance(p[0],bytes)]
                for block in blocks:
                    for filename in bodystructure_filenames(block):
                        filename_candidates+=1
                        parsed=extract(filename)
                        if not parsed:
                            # An H identifier may be absent from the attachment filename.
                            # Corroborate invoice/AMEA with the same email subject and
                            # require an explicit KRW amount in filename; never guess.
                            status_hdr, hdr = im.uid("FETCH",uid,"(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                            payload = next((v[1] for v in hdr or [] if isinstance(v,tuple) and isinstance(v[1],bytes)),None)
                            subject = ""
                            if status_hdr=="OK" and payload:
                                subject=str(BytesParser(policy=default).parsebytes(payload,headersonly=True).get("Subject",""))
                            parsed=corroborated_filename(filename,subject)
                            if parsed:
                                fallback_matched+=1
                            else:
                                reject_reasons["PATTERN_MISMATCH"]+=1
                                if "AMEA" not in filename.upper():reject_reasons["MISSING_AMEA"]+=1
                                if "KRW" not in filename.upper():reject_reasons["MISSING_KRW"]+=1
                                if not re.search(r"H[0-9]{5,}",filename,re.I):reject_reasons["MISSING_H"]+=1
                                continue
                        inv,hnum,po,amea,amount,state=parsed
                        if state not in ("FILENAME_PARSED","SUBJECT_CORROBORATED_FILENAME"):
                            reject_reasons[state]+=1
                            continue
                        filename_parsed+=1
                        issued=filename # attachment lacks issue date; use IMAP INTERNALDATE month below
                        status,dtparts=im.uid("FETCH",uid,"(INTERNALDATE)")
                        dates=" ".join(p[0].decode("utf-8","replace") if isinstance(p,tuple) else p.decode("utf-8","replace") for p in dtparts if isinstance(p,(tuple,bytes))) if status=="OK" else ""
                        found_dt=re.search(r'INTERNALDATE "([0-9]{2}-[A-Za-z]{3}-[0-9]{4})',dates)
                        month=""
                        if found_dt:
                            try:month=dt.datetime.strptime(found_dt.group(1),"%d-%b-%Y").strftime("%Y-%m")
                            except ValueError:pass
                        row=[inv,month,str(amount),amea,hnum,po,folder,uid.decode(),filename,state,dt.datetime.now(dt.timezone.utc).isoformat()]
                        previous=by_invoice.get(inv)
                        if previous and previous[2]!=str(amount):
                            print("QQ_BACKFILL_CONFLICT invoice_hash_suffix="+inv[-4:],flush=True)
                            continue
                        if not previous:by_invoice[inv]=row;fetched+=1
                if scanned>=limit:break
        im.logout()
    print("QQ_BACKFILL_PARSER_DIAGNOSTIC "+json.dumps(dict(sorted(reject_reasons.items())),sort_keys=True)+" fallback_verified="+str(fallback_matched),flush=True)
    print("QQ_BACKFILL_DIAGNOSTIC year="+str(year)+" folders="+str(folders)+" matches="+str(matches)+" scanned="+str(scanned)+" attachment_candidates="+str(filename_candidates)+" parsed_invoices="+str(filename_parsed)+" new="+str(fetched),flush=True)
    if not by_invoice and (matches==0 or (scanned>0 and filename_parsed==0)):
        raise RuntimeError("QQ_BACKFILL_NO_INVOICE_EVIDENCE_CHECK_SUBJECT_SEARCH_OR_BODYSTRUCTURE")
    values=[HEAD]+list(by_invoice.values())
    if len(values)>10000:raise RuntimeError("BACKFILL_ROWS_EXCEED_LIMIT")
    call(s,"PUT","/values/"+quote("A1")+"?valueInputOption=RAW",json={"values":values})
    # Write invoice evidence first. Only then persist scan cursors and audit.
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    for folder,(uidval,last_uid) in last_by_folder.items():
        cursors[(year,folder)]=[str(year),folder,uidval,str(last_uid),now]
    cursor_values=[cursor_header]+[cursors[key] for key in sorted(cursors)]
    if len(cursor_values)>1000:raise RuntimeError("CURSOR_CAPACITY")
    def sheet_a1(tab):
        return urllib.parse.quote("'"+tab+"'!A1",safe="")
    call(s,"PUT","/values/"+sheet_a1(CURSOR_TAB)+"?valueInputOption=RAW",json={"values":cursor_values})
    status_label="PARTIAL_SCAN" if unfinished else "SCAN_COMPLETE"
    audit_by_year[str(year)]=[str(year),now,status_label,matches,scanned,filename_candidates,filename_parsed,fetched]
    audit_values=[audit_header]+[audit_by_year[key] for key in sorted(audit_by_year)]
    call(s,"PUT","/values/"+sheet_a1(AUDIT_TAB)+"?valueInputOption=RAW",json={"values":audit_values})
    print("QQ_BACKFILL_"+status_label+" year="+str(year)+" folders="+str(folders)+" candidates="+str(matches)+" scanned="+str(scanned)+" new="+str(fetched)+" total="+str(len(by_invoice))+" checkpoint_folders="+str(len(last_by_folder))+" prior_skipped="+str(prior_skipped)+" missing_uidvalidity_folders="+str(no_uidvalidity_folders))
if __name__=="__main__":main()
