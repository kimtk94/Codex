#!/usr/bin/env python3
"""Read-only historical QQ TAX INVOICE backfill; never changes source or mail."""
import datetime as dt, imaplib, json, os, re, sys, urllib.parse
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from tax_invoice_extract import extract,bodystructure_filenames

SHEET=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
TAB="QQ Historical Invoice Backfill"
HEAD=["invoice_number","issued_month","amount_krw","amea_project_id","h_project_id","po_reference","imap_folder","imap_uid","filename","evidence","backfill_utc"]
def call(session,method,path,**kw):
    url="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+path
    resp=session.request(method,url,timeout=65,**kw)
    if not resp.ok:raise RuntimeError("SHEETS_"+str(resp.status_code)+" "+resp.text[:220])
    return resp.json() if resp.content else {}
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
    scanned=0; matches=0; fetched=0; folders=0; limit=int(os.getenv("BACKFILL_MAX_MATCHES","2500"))
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        status,listing=im.list()
        if status!="OK":raise RuntimeError("IMAP_LIST_FAILED")
        names=[]
        for item in listing or []:
            line=item.decode("utf-8","replace")
            mt=re.search(r' (?:"([^"]+)"|([^ "]+))$',line)
            if mt:names.append(mt.group(1) or mt.group(2))
        for folder in names:
            status,_=im.select('"'+folder.replace('"','')+'"',readonly=True)
            if status!="OK":continue
            folders+=1
            start=f"01-Jan-{year}";end=f"01-Jan-{year+1}"
            # Broad subject search to find invoice notifications independent of sender.
            found=set()
            for phrase in ('Invoice Issued','TAX INVOICE'):
                status,found_rows=im.uid("SEARCH",None,"SINCE",start,"BEFORE",end,"SUBJECT",'"'+phrase+'"')
                if status=="OK":found.update((found_rows[0] or b"").split())
            matches+=len(found)
            print("QQ_BACKFILL_FOLDER folder_count="+str(folders)+" candidates="+str(len(found)),flush=True)
            for uid in sorted(found,key=lambda x:int(x)):
                if scanned>=limit:break
                scanned+=1
                status,parts=im.uid("FETCH",uid,"(BODYSTRUCTURE)")
                if status!="OK":continue
                blocks=[p for p in parts if isinstance(p,bytes)]
                blocks +=[p[0] for p in parts if isinstance(p,tuple) and isinstance(p[0],bytes)]
                for block in blocks:
                    for filename in bodystructure_filenames(block):
                        parsed=extract(filename)
                        if not parsed:continue
                        inv,hnum,po,amea,amount,state=parsed
                        if state!="FILENAME_PARSED":continue
                        issued=filename # attachment lacks issue date; use IMAP INTERNALDATE month below
                        status,dtparts=im.uid("FETCH",uid,"(INTERNALDATE)")
                        dates=" ".join(p[0].decode("utf-8","replace") if isinstance(p,tuple) else p.decode("utf-8","replace") for p in dtparts if isinstance(p,(tuple,bytes))) if status=="OK" else ""
                        found_dt=re.search(r'INTERNALDATE "([0-9]{2}-[A-Za-z]{3}-[0-9]{4})',dates)
                        month=""
                        if found_dt:
                            try:month=dt.datetime.strptime(found_dt.group(1),"%d-%b-%Y").strftime("%Y-%m")
                            except ValueError:pass
                        row=[inv,month,str(amount),amea,hnum,po,folder,uid.decode(),filename,"ATTACHMENT_FILENAME_ONLY",dt.datetime.now(dt.timezone.utc).isoformat()]
                        previous=by_invoice.get(inv)
                        if previous and previous[2]!=str(amount):
                            print("QQ_BACKFILL_CONFLICT invoice_hash_suffix="+inv[-4:],flush=True)
                            continue
                        if not previous:by_invoice[inv]=row;fetched+=1
                if scanned>=limit:break
            if scanned>=limit:break
        im.logout()
    values=[HEAD]+list(by_invoice.values())
    if len(values)>10000:raise RuntimeError("BACKFILL_ROWS_EXCEED_LIMIT")
    call(s,"PUT","/values/"+quote("A1")+"?valueInputOption=RAW",json={"values":values})
    print("QQ_BACKFILL_PASS year="+str(year)+" folders="+str(folders)+" candidates="+str(matches)+" scanned="+str(scanned)+" new="+str(fetched)+" total="+str(len(by_invoice))+" capped="+str(scanned>=limit))
if __name__=="__main__":main()
