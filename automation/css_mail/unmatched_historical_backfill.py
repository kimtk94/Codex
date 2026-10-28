#!/usr/bin/env python3
"""Append only current QQ UIDs not found in either legacy or staging source."""
import datetime as dt
import imaplib
import os
import urllib.parse
from email.parser import BytesParser
from email.policy import default
import incremental_sync as src
from legacy_uid_full_coverage import read_legacy_keys

def main():
    s=src.authorize()
    src.ensure_tab(s)
    staged=src.existing_keys(s)
    legacy=read_legacy_keys(s)
    added=[]
    limit=min(int(os.getenv("CSS_UNMATCHED_BACKFILL_LIMIT","120")),200)
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        folders=src.folder_names(im)
        sent=next((f for f,t in folders if "\\sent" in t or f.lower() in ("sent messages","sent","sent items")),None)
        if not sent:raise RuntimeError("SENT_FOLDER_MISSING")
        for direction,folder in (("INBOUND","INBOX"),("OUTBOUND",sent)):
            if len(added)>=limit:break
            status,_=im.select('"'+folder.replace('"','')+'"',readonly=True)
            if status!="OK":raise RuntimeError("SELECT_FAILED")
            _,uv=im.response("UIDVALIDITY")
            validity=uv[0].decode("ascii","replace")
            status,hits=im.uid("SEARCH",None,"ALL")
            if status!="OK":raise RuntimeError("SEARCH_FAILED")
            for raw_uid in (hits[0] or b"").split():
                uid=raw_uid.decode("ascii")
                key=folder+"|"+validity+"|"+uid
                if key in staged or uid in legacy["INBOX" if direction=="INBOUND" else "SENT"]:continue
                status,payload=im.uid("FETCH",raw_uid,"(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES DATE FROM TO CC SUBJECT)])")
                if status!="OK":raise RuntimeError("FETCH_FAILED")
                blob=next((x[1] for x in payload if isinstance(x,tuple) and isinstance(x[1],bytes)),None)
                if not blob:raise RuntimeError("HEADER_MISSING")
                msg=BytesParser(policy=default).parsebytes(blob,headersonly=True)
                subject=str(msg.get("Subject",""))[:500]
                added.append([key,str(msg.get("Message-ID",""))[:300],uid,folder,validity,src.date_str(msg.get("Date")),
                    src.decode_address(msg.get("From")),src.decode_address(msg.get("To")),src.decode_address(msg.get("Cc")),subject,
                    src.pattern(r"AMEA\d{7,}",subject),src.pattern(r"H\d{3}SC\d{5,}",subject),
                    src.pattern(r"SAM\d{4,}",subject),src.pattern(r"BATCH\d{4,}",subject),
                    dt.datetime.now(dt.timezone.utc).isoformat(),direction,
                    str(msg.get("In-Reply-To",""))[:500],str(msg.get("References",""))[:2000]])
                if len(added)>=limit:break
        im.logout()
    latest=src.existing_keys(s)
    safe=[r for r in added if r[0] not in latest]
    if safe:
        q=urllib.parse.quote("'"+src.TAB+"'!A:R",safe="")
        src.api(s,"POST",src.endpoint("/values/"+q+":append")+"?valueInputOption=RAW&insertDataOption=INSERT_ROWS",json={"values":safe})
    print("QQ_UNMATCHED_BACKFILL_PASS selected="+str(len(added))+" appended="+str(len(safe))+" limit="+str(limit)+" source=full_imap_uid_coverage")
if __name__=="__main__":main()
