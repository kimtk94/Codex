#!/usr/bin/env python3
"""Read-only confirmation pending statement money and direct-recipient evidence."""
import imaplib,re,json,os,urllib.parse,html
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
import incremental_sync as src
BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
PERSON="taehoon.kim@novogene.com"
def body_text(msg):
    texts=[]
    for part in msg.walk():
        if part.get_content_maintype()=="text":
            try:texts.append(part.get_content())
            except Exception:continue
    result=[]
    for t in texts:
        v=re.sub(r"<[^>]+>"," ",str(t))
        v=html.unescape(re.sub(r"\s+"," ",v))
        result.append(v)
    return " ".join(result)[:100000]
def main():
    s=src.authorize()
    url="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+urllib.parse.quote("'Confirmation Evidence Ledger'!A1:E100",safe="")
    r=s.request("GET",url,timeout=90);r.raise_for_status()
    ameas=[x[0] for x in r.json().get("values",[])[1:] if x and x[0]]
    out=[]
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        im.select("INBOX",readonly=True)
        for amea in ameas:
            hits=set()
            for phrase in (amea,):
                st,found=im.uid("SEARCH",None,"SUBJECT",'"'+phrase+'"')
                if st=="OK":hits.update((found[0] or b"").split())
            events=[]
            for uid in sorted(hits,key=int,reverse=True)[:35]:
                st,parts=im.uid("FETCH",uid,"(BODY.PEEK[])")
                if st!="OK":continue
                data=next((p[1] for p in parts or [] if isinstance(p,tuple) and isinstance(p[1],bytes)),None)
                if not data:continue
                msg=BytesParser(policy=default).parsebytes(data)
                subj=str(msg.get("Subject",""))
                if not re.search(r"(?<![A-Za-z0-9])"+re.escape(amea)+r"(?![0-9])",subj,re.I):continue
                if "Statement Ready For Confirmation" not in subj and "Invoice Issued" not in subj:continue
                tos={a.lower() for _,a in getaddresses([str(msg.get("To","")),str(msg.get("Cc",""))])}
                original=(not re.match(r"^\s*(re|fw|fwd|회신|답장|전달)\s*[:：]",subj,re.I) and not msg.get("In-Reply-To"))
                text=body_text(msg)
                match=re.search(r"Total\s*Amount.{0,100}?([0-9][0-9,]{2,}(?:\.\d{1,2})?)\s*(KRW|USD)",text,re.I)
                money=match.group(1) if match else None
                currency=match.group(2).upper() if match else None
                events.append({"kind":"INVOICE_ISSUED" if "Invoice Issued" in subj else "CONFIRMATION_REQUEST",
                    "uid":uid.decode(),"personal_direct_recipient":PERSON in tos,
                    "original":bool(original),"amount":money,"currency":currency,
                    "amount_extraction":"BODY_TOTAL_AMOUNT" if match else "NOT_EXTRACTED"})
            out.append({"amea":amea,"events":events[:10],"matched_events":len(events)})
        im.logout()
    print("QQ_PENDING_CONFIRMATION_AUDIT "+json.dumps({"results":out,"rule":"To/Cc personal direct + original CSS sender required; forecast not counted as statement"}))
if __name__=="__main__":main()
