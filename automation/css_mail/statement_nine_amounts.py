#!/usr/bin/env python3
"""Read-only nine exact QQ statement emails; disclose aggregate amount evidence only."""
import imaplib,json,os,re,html
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
UIDS={"40004":"AMEA2026090717","40153":"AMEA2026101340","40156":"AMEA2026073102","40167":"AMEA2026092814","40256":"AMEA2026042239","40429":"AMEA2026091713","40570":"AMEA2026091512","40633":"AMEA2026083104","40662":"AMEA2026081017"}
def content(msg):
    arr=[]
    for p in msg.walk():
        if p.get_content_maintype()!="text" or p.get_content_disposition()=="attachment":continue
        try:
            text=p.get_content()
            if p.get_content_subtype()=="html":
                text=re.sub(r"</(?:td|th|tr|p|div|table)>"," ",text,flags=re.I)
                text=re.sub(r"<[^>]+>"," ",text)
            arr.append(html.unescape(str(text)))
        except Exception:continue
    return " ".join(arr)
def main():
    results=[]
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        im.select("INBOX",readonly=True)
        for uid,amea in UIDS.items():
            status,parts=im.uid("FETCH",uid,"(BODY.PEEK[])")
            payload=next((x[1] for x in parts or [] if isinstance(x,tuple) and isinstance(x[1],bytes)),None)
            if status!="OK" or not payload:
                results.append({"amea":amea,"uid":uid,"state":"FETCH_FAILED"});continue
            msg=BytesParser(policy=default).parsebytes(payload)
            subject=str(msg.get("Subject",""))
            recipients={x.lower() for _,x in getaddresses([str(msg.get("To","")),str(msg.get("Cc",""))])}
            sender={x.lower() for _,x in getaddresses([str(msg.get("From",""))])}
            if amea not in subject or "Statement Ready For Confirmation" not in subject or "css@novogene-amea.com" not in sender or "taehoon.kim@novogene.com" not in recipients:
                results.append({"amea":amea,"uid":uid,"state":"IDENTITY_MISMATCH"});continue
            text=content(msg)
            # Require an explicit label and currency; don't treat quote, subtotals or unrelated amounts as confirmed.
            candidates=[]
            for m in re.finditer(r"Total\s*Amount\s*[:：]?\s*(?:KRW\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)\s*(KRW|USD)?",text,re.I):
                candidates.append({"amount":m.group(1).replace(",",""),"currency":(m.group(2) or "KRW").upper()})
            for m in re.finditer(r"Total\s*Amount\s*[:：]?\s*(KRW|USD)\s*([0-9][0-9,]*(?:\.\d{1,2})?)",text,re.I):
                candidates.append({"amount":m.group(2).replace(",",""),"currency":m.group(1).upper()})
            unique=list({(c["amount"],c["currency"]):c for c in candidates}.values())
            state="VERIFIED_TOTAL" if len(unique)==1 else ("NO_TOTAL" if not unique else "MULTIPLE_TOTALS")
            results.append({"amea":amea,"uid":uid,"state":state,"total":unique[0] if len(unique)==1 else None,"candidate_count":len(unique)})
        im.logout()
    print("QQ_NINE_STATEMENT_AMOUNTS "+json.dumps(results,ensure_ascii=True))
if __name__=="__main__":main()
