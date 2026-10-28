#!/usr/bin/env python3
"""Read-only: derive personally addressed original statements by UID, parse table totals."""
import imaplib,os,re,html,json,urllib.parse
from email.parser import BytesParser
from email.policy import default
import incremental_sync as src
BOOK=os.environ.get("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
ADDR="taehoon.kim@novogene.com"
def rows(sess,tab,range_):
 u="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+urllib.parse.quote("'"+tab+"'!"+range_,safe="")
 r=sess.request("GET",u,timeout=90);r.raise_for_status()
 return r.json().get("values",[])
def ids(s):return re.findall(r"AMEA[0-9]{8}(?:-[0-9]{1,3})?",str(s),re.I)
def main():
 sess=src.authorize()
 mail=rows(sess,"CSS Git Ingest","A1:Q12000")
 invoice=rows(sess,"CSS Tax Invoice List","A1:N1000")
 issued={x[4].upper() for x in invoice[1:] if len(x)>4 and x[4]}
 candidates=[]
 for r in mail[1:]:
  r=r+[""]*(17-len(r))
  subject=str(r[9]);recipient=(str(r[7])+" "+str(r[8])).lower()
  if r[6]!="css@novogene-amea.com" or ADDR not in recipient or r[16]:continue
  if not re.search(r"Final Report & Statement Ready For Confirmation",subject,re.I):continue
  if re.match(r"^\s*(RE|FW|FWD)\s*:",subject,re.I):continue
  projects=ids(subject)
  if len(projects)!=1 or projects[0].upper() in issued:continue
  candidates.append((r[2],projects[0].upper(),subject))
 dedup={uid:(uid,project,subject) for uid,project,subject in candidates}
 result=[]
 with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=60) as im:
  im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
  im.select("INBOX",readonly=True)
  for uid,project,subject in dedup.values():
   st,parts=im.uid("FETCH",uid,"(BODY.PEEK[])")
   payload=next((p[1] for p in parts or [] if isinstance(p,tuple) and isinstance(p[1],bytes)),None)
   if st!="OK" or not payload:
    result.append({"amea":project,"status":"FETCH_FAILED"});continue
   msg=BytesParser(policy=default).parsebytes(payload)
   actual=str(msg.get("Subject",""))
   if project not in actual or "Statement Ready For Confirmation" not in actual:
    result.append({"amea":project,"status":"SUBJECT_MISMATCH"});continue
   fragments=[]
   for part in msg.walk():
    if part.get_content_type() in ("text/plain","text/html"):
     try:fragments.append(str(part.get_content()))
     except Exception:pass
   body=html.unescape(" ".join(fragments))
   body=re.sub(r"<[^>]*>"," ",body)
   body=re.sub(r"\s+"," ",body)
   matches=re.findall(r"Total\s*Amount\s*[:：]?\s*(?:KRW\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(KRW)?",body,re.I)
   totals={int(float(n.replace(",",""))) for n,c in matches if float(n.replace(",","")).is_integer()}
   result.append({"amea":project,"uid":uid,"total_krw":next(iter(totals)) if len(totals)==1 else None,
                  "status":"TOTAL_VERIFIED" if len(totals)==1 else "TOTAL_REVIEW","total_candidates":len(totals)})
  im.logout()
 print("QQ_PERSONAL_STATEMENTS "+json.dumps({"candidate_messages":len(dedup),
   "amount_verified":sum(r["status"]=="TOTAL_VERIFIED" for r in result),
   "verified_sum_krw":sum(r.get("total_krw") or 0 for r in result),
   "results":result},ensure_ascii=False))
if __name__=="__main__":main()
