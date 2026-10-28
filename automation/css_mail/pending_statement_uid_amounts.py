#!/usr/bin/env python3
"""Read-only proof of pending Statement/Confirmation amounts by known IMAP UID."""
import imaplib,json,os,re,urllib.parse,html
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
import incremental_sync as src

BOOK="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
PERSON="taehoon.kim@novogene.com"
def getrows(session,tab,last):
    url="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+urllib.parse.quote("'"+tab+"'!A1:"+last,safe="")
    response=session.request("GET",url,timeout=90);response.raise_for_status()
    return response.json().get("values",[])[1:]
def amea(v):
    found=re.search(r"AMEA\d{7,}(?:-\d{1,3})?",str(v or ""),re.I)
    return found.group(0).upper() if found else ""
def personal(row):
    return PERSON in (str(row[7] or "")+" "+str(row[8] or "")).lower()
def original(row):
    return (str(row[6] or "").lower()=="css@novogene-amea.com" and personal(row)
            and not (len(row)>16 and row[16])
            and not re.match(r"^\s*(re|fw|fwd|회신|답장|전달)\s*[:：]",str(row[9] or ""),re.I))
def textparts(msg):
    found=[]
    for part in msg.walk():
        if part.get_content_type() not in ("text/html","text/plain"):continue
        try:
            body=str(part.get_content())
            body=re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>"," ",body)
            body=re.sub(r"(?i)</(?:td|th|tr|p|div|br|table)>"," ",body)
            body=re.sub(r"<[^>]*>"," ",body)
            found.append(html.unescape(re.sub(r"\s+"," ",body)))
        except Exception:pass
    return found
def amounts(msg):
    found=[]
    for text in textparts(msg):
        for m in re.finditer(r"Total\s*Amount\b",text,re.I):
            nearby=text[m.end():m.end()+240]
            for pat in [r"^\s*[:：]?\s*(?:KRW\s*)?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(KRW|USD)?\b",
                        r"^\s*[:：]?\s*(KRW|USD)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\b"]:
                x=re.search(pat,nearby,re.I)
                if x:
                    a,b=x.groups()
                    number=a if re.match(r"^\d",a) else b
                    unit=b if number==a else a
                    try:val=float(number.replace(",",""))
                    except ValueError:continue
                    if val>0:found.append((round(val,2),str(unit or "").upper()))
    return sorted(set(found))
def main():
    session=src.authorize()
    mail=getrows(session,"CSS Git Ingest","Q12000")
    inv=getrows(session,"CSS Tax Invoice List","N1000")
    known={str(r[4]).upper() for r in inv if len(r)>4 and r[4]}
    candidates=[]
    for r in mail:
        if len(r)<10 or not original(r) or "Final Report & Statement Ready For Confirmation" not in str(r[9]):continue
        key=amea(r[9])
        if key and key not in known:candidates.append((key,str(r[2]),str(r[9]),str(r[5])))
    unique={}
    for item in candidates:unique[(item[0],item[1])]=item
    results=[]
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        im.select("INBOX",readonly=True)
        for key,uid,subject,date in unique.values():
            status,parts=im.uid("FETCH",uid,"(BODY.PEEK[])")
            payload=next((v[1] for v in parts or [] if isinstance(v,tuple) and isinstance(v[1],bytes)),None)
            if status!="OK" or not payload:
                results.append({"amea":key,"uid":uid,"status":"MAIL_UNAVAILABLE"});continue
            msg=BytesParser(policy=default).parsebytes(payload)
            real_subject=str(msg.get("Subject",""))
            receivers={a.lower() for _,a in getaddresses([str(msg.get("To","")),str(msg.get("Cc",""))])}
            senders={a.lower() for _,a in getaddresses([str(msg.get("From",""))])}
            if (key not in real_subject.upper() or PERSON not in receivers
                or "css@novogene-amea.com" not in senders or msg.get("In-Reply-To")):
                results.append({"amea":key,"uid":uid,"status":"ORIGINAL_IDENTITY_MISMATCH"});continue
            nums=amounts(msg)
            results.append({"amea":key,"uid":uid,"status":"TOTAL_AMOUNT_FOUND" if nums else "AMOUNT_NOT_FOUND","totals":nums})
        im.logout()
    verified=[r for r in results if r["status"]=="TOTAL_AMOUNT_FOUND" and len(r["totals"])==1 and r["totals"][0][1]=="KRW"]
    print("PENDING_STATEMENT_UID_AMOUNT_AUDIT "+json.dumps({
        "candidate_statement_events":len(unique),"projects":len(set(x[0] for x in unique.values())),
        "total_rows_with_one_krw_amount":len(verified),
        "total_krw_confirmed_excluding_issued_amea":sum(int(r["totals"][0][0]) for r in verified),
        "results":results},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
