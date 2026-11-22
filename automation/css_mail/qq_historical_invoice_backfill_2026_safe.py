#!/usr/bin/env python3
"""QQ invoice evidence writer: read-only source IMAP, guarded Google Sheets outputs."""
import datetime as dt, imaplib, json, os, re, sys, urllib.parse
from collections import Counter
from email.parser import BytesParser
from email.policy import default
from invoice_fallback import corroborated_filename
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from tax_invoice_extract import extract,bodystructure_filenames,imap_bodystructure_chunks
from qq_safe_backfill_ingest import evaluate_candidate,safe_folder_checkpoint

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
    mode=os.getenv("BACKFILL_WRITE_MODE","PREVIEW").strip().upper()
    if mode not in ("PREVIEW","APPLY"):
        raise RuntimeError("BACKFILL_WRITE_MODE_INVALID")
    if mode=="APPLY" and os.getenv("BACKFILL_STAGE_WRITES_APPROVED","")!="YES":
        raise RuntimeError("BACKFILL_WRITER_APPROVAL_GATE")
    cred=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    s=AuthorizedSession(cred)
    meta=call(s,"GET","?fields=sheets.properties.title")
    if TAB not in {x["properties"]["title"] for x in meta["sheets"]}:
        if mode=="PREVIEW":
            raise RuntimeError("BACKFILL_PREVIEW_SOURCE_TAB_MISSING")
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
            if mode=="PREVIEW":
                raise RuntimeError("BACKFILL_PREVIEW_AUDIT_TAB_MISSING")
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
    # Existing historical rows were already validated; avoid refetching them.
    # These UID hints never advance the cursor and do not imply full coverage.
    known_uids={(str(r[6]),str(r[7])) for r in by_invoice.values()
                if len(r)>7 and r[6] and str(r[7]).isdigit()}
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
        # Never write seeded evidence before IMAP preflight and source review.
        # Persist the merged in-memory rows once, before the safe cursor.
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
                print("QQ_BACKFILL_WARNING UIDVALIDITY unavailable; cursor disabled for folder="+str(folders),flush=True)
            old_cursor=cursors.get((year,folder))
            checkpoint=int(old_cursor[3]) if old_cursor and old_cursor[2]==uidvalidity else 0
            start=f"01-Jan-{year}";end=f"01-Jan-{year+1}"
            # Broad subject search to find invoice notifications independent of sender.
            found=set()
            for phrase in ('Invoice Issued','TAX INVOICE'):
                status,found_rows=im.uid("SEARCH",None,"SINCE",start,"BEFORE",end,"SUBJECT",'"'+phrase+'"')
                if status!="OK" or not found_rows or not isinstance(found_rows[0],bytes):
                    raise RuntimeError("QQ_BACKFILL_SEARCH_UNAVAILABLE")
                found.update(found_rows[0].split())
            matches+=len(found)
            print("QQ_BACKFILL_FOLDER folder_count="+str(folders)+" candidates="+str(len(found)),flush=True)
            eligible=[u for u in sorted(found,key=lambda x:int(x)) if int(u)>checkpoint]
            # Missing UIDVALIDITY is not an incomplete scan when this folder has no candidates.
            # For folders with candidates, retain failure until identity/cursor safety is resolved.
            if not uidvalidity and eligible:
                unfinished=True
            prior_skipped+=len(found)-len(eligible)
            if scanned>=limit and eligible:unfinished=True
            # Process the sorted source UIDs, but preserve a retryable hole
            # instead of silently advancing the cursor before FETCH/parsing.
            processed_uids=[]
            outcomes={}
            if not uidvalidity and eligible:
                unfinished=True
                continue
            for uid in eligible:
                if scanned>=limit:
                    unfinished=True
                    break
                uid_int=int(uid)
                uid_text=uid.decode("ascii")
                already_evidenced=(folder,uid_text) in known_uids
                if not already_evidenced:
                    scanned+=1
                state, staged, diag=evaluate_candidate(
                    im,uid_text,folder,already_evidenced,
                    imap_bodystructure_chunks,bodystructure_filenames,
                    extract,corroborated_filename,by_invoice)
                processed_uids.append(uid_int)
                outcomes[uid_int]=state
                reject_reasons[state]+=1
                if "arrival_metadata_state" in diag:
                    reject_reasons["ARRIVAL_"+diag["arrival_metadata_state"]]+=1
                if state=="ORIGINAL_ISSUED_PROOF_PERSISTED":
                    # Per-message staging is atomic in memory: if any
                    # attachment conflicts, none of its invoice rows are added.
                    for row in staged:
                        filename_candidates+=1
                        filename_parsed+=1
                        if row[9]=="SUBJECT_CORROBORATED_FILENAME":
                            fallback_matched+=1
                        if row[0] not in by_invoice:
                            by_invoice[row[0]]=row
                            fetched+=1
                    known_uids.add((folder,uid_text))
                if state not in (
                    "KNOWN_UID_WITH_VALID_EVIDENCE",
                    "ORIGINAL_ISSUED_PROOF_PERSISTED",
                    "ORIGINAL_NONOFFICIAL_HEADER_VERIFIED"):
                    unfinished=True
                    # Stop at the first unresolved UID. Later UID successes
                    # must not move the durable cursor across this gap.
                    break
            if processed_uids:
                decision=safe_folder_checkpoint(checkpoint,processed_uids,outcomes)
                if decision["checkpoint_safe"]>checkpoint:
                    last_by_folder[folder]=(
                        uidvalidity,decision["checkpoint_safe"])
                if decision["blocked"]:
                    unfinished=True
            if scanned>=limit and len(processed_uids)<len(eligible):
                unfinished=True
        im.logout()
    print("QQ_BACKFILL_PARSER_DIAGNOSTIC "+json.dumps(dict(sorted(reject_reasons.items())),sort_keys=True)+" fallback_verified="+str(fallback_matched),flush=True)
    print("QQ_BACKFILL_DIAGNOSTIC year="+str(year)+" folders="+str(folders)+" matches="+str(matches)+" scanned="+str(scanned)+" attachment_candidates="+str(filename_candidates)+" parsed_invoices="+str(filename_parsed)+" new="+str(fetched),flush=True)
    if not by_invoice and (matches==0 or (scanned>0 and filename_parsed==0)):
        raise RuntimeError("QQ_BACKFILL_NO_INVOICE_EVIDENCE_CHECK_SUBJECT_SEARCH_OR_BODYSTRUCTURE")
    values=[HEAD]+list(by_invoice.values())
    if len(values)>10000:raise RuntimeError("BACKFILL_ROWS_EXCEED_LIMIT")
    if mode=="PREVIEW":
        # The scan used read-only IMAP and Sheets GET only: no JSON payload
        # contains raw invoices, customers or UID identifiers in CI output.
        print("QQ_BACKFILL_PROOF_FIRST_PREVIEW year="+str(year)+
              " scanned="+str(scanned)+
              " new_in_memory="+str(fetched)+
              " would_update_cursor_folders="+str(len(last_by_folder))+
              " blocked="+str(int(unfinished))+
              " sheet_writes=0 cursor_writes=0",flush=True)
        # A preview has not updated the QQ Backfill source or audit cursor.
        # Exit nonzero even on a clean probe so upstream chain consumers do
        # not misread it as an authoritative successful data collection.
        print("QQ_BACKFILL_PREVIEW_ONLY_NOT_COMMITTED",flush=True)
        sys.exit(2)
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
    # A partial scan must never appear as a successful complete backfill in Actions.
    # Keep persisted evidence/cursors for incremental continuation, but fail the run.
    if unfinished:
        print("QQ_BACKFILL_INCOMPLETE: audit and cursors preserved; rerun required",file=sys.stderr,flush=True)
        sys.exit(2)
if __name__=="__main__":main()
