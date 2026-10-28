#!/usr/bin/env python3
"""Read-only exact-UID Statement amount investigation; outputs no customer mail text."""
import imaplib, os, re, json
from email.parser import BytesParser
from email.policy import default
from bs4 import BeautifulSoup

TARGETS={"AMEA2026083104":"40633","AMEA2026081017":"40662","AMEA2026082719":"39664"}
def text_parts(msg):
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition()=="attachment":continue
        if part.get_content_type() not in ("text/html","text/plain"):continue
        try:
            body=part.get_content()
            if part.get_content_type()=="text/html":body=BeautifulSoup(body,"html.parser").get_text(" ",strip=True)
            yield re.sub(r"\s+"," ",body)
        except Exception:continue
def main():
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        if im.select("INBOX",readonly=True)[0]!="OK":raise RuntimeError("INBOX_MISSING")
        for amea,uid in TARGETS.items():
            ok,items=im.uid("FETCH",uid,"(BODY.PEEK[])")
            if ok!="OK":raise RuntimeError("FETCH_FAILED")
            raw=next((x[1] for x in items or [] if isinstance(x,tuple) and isinstance(x[1],bytes)),None)
            if not raw:
                print("STATEMENT_AMOUNT "+json.dumps({"amea":amea,"status":"MESSAGE_NOT_FOUND"}));continue
            msg=BytesParser(policy=default).parsebytes(raw)
            subj=str(msg.get("Subject",""))
            if not subj.startswith("❗️Action Required: Final Report & Statement Ready For Confirmation") or str(msg.get("In-Reply-To","")):
                print("STATEMENT_AMOUNT "+json.dumps({"amea":amea,"status":"NOT_FIRST_STATEMENT_NOTICE"}));continue
            contexts=[]
            for body in text_parts(msg):
                for match in list(re.finditer(r"(?i)total\s*amount",body))[:8]:
                    near=body[match.end():match.end()+140]
                    numbers=re.findall(r"(?:KRW\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:KRW)?",near,re.I)
                    contexts.append({"numeric_candidates":numbers[:6],"krw_present":bool(re.search("KRW",near,re.I))})
            print("STATEMENT_AMOUNT "+json.dumps({"amea":amea,"status":"SOURCE_BODY_READ","contexts":contexts[:6]}))
        im.logout()
if __name__=="__main__":main()
