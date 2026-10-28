#!/usr/bin/env python3
"""Read-only QQ mailbox UID coverage against CSS Git Ingest, no 60-day window."""
import imaplib,json,os,urllib.parse
from collections import Counter
import incremental_sync as src

def audit():
    s=src.authorize()
    q=urllib.parse.quote("'"+src.TAB+"'!A1:R100000",safe="")
    raw=src.api(s,"GET",src.endpoint("/values/"+q)).get("values",[])
    if not raw or raw[0]!=src.COLS:raise RuntimeError("STAGING_SCHEMA_MISMATCH")
    keys={str(r[0]) for r in raw[1:] if r}
    results=[]
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        folders=src.folder_names(im)
        sent=next((f for f,t in folders if "\\sent" in t or f.lower() in ("sent messages","sent","sent items")),None)
        if not sent:raise RuntimeError("SENT_FOLDER_MISSING")
        for folder in ["INBOX",sent]:
            status,_=im.select('"'+folder.replace('"','')+'"',readonly=True)
            if status!="OK":raise RuntimeError("SELECT_FAILED")
            _,uv=im.response("UIDVALIDITY")
            validity=uv[0].decode("ascii","replace")
            status,hits=im.uid("SEARCH",None,"ALL")
            if status!="OK":raise RuntimeError("FULL_UID_SEARCH_FAILED")
            uids=(hits[0] or b"").split()
            missing=[u.decode("ascii") for u in uids if folder+"|"+validity+"|"+u.decode("ascii") not in keys]
            results.append({"folder":"INBOX" if folder=="INBOX" else "SENT",
                "imap_total":len(uids),"staging_covered":len(uids)-len(missing),
                "not_in_staging":len(missing),"uidvalidity_present":bool(validity)})
        im.logout()
    print("QQ_FULL_MAILBOX_UID_COVERAGE "+json.dumps({
        "folders":results,
        "all_uids_in_staging":all(x["not_in_staging"]==0 for x in results),
        "scope_note":"Compares full current IMAP INBOX/Sent UIDs to staging, not historical legacy-only records; message bodies/attachments not downloaded."
    },sort_keys=True))
if __name__=="__main__":audit()
