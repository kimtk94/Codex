#!/usr/bin/env python3
"""Read-only source IMAP proof for historical TAX INVOICE records. No Revenue writes."""
import imaplib,json,os,re,urllib.parse
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
import incremental_sync as src
from tax_invoice_extract import extract,bodystructure_filenames,original_issued_mail

def main():
    s=src.authorize()
    path=urllib.parse.quote("'CSS Tax Invoice List'!A1:N12000",safe="")
    values=src.api(s,"GET",src.endpoint("/values/"+path)).get("values",[])
    if not values or values[0][2]!="invoice_number":raise RuntimeError("INVOICE_LEDGER_SCHEMA_CHANGED")
    records=[dict(zip(values[0],r)) for r in values[1:] if r]
    limit=min(max(1,int(os.getenv("CSS_INVOICE_PROOF_BATCH","400"))),500)
    checked=0;proof=0;failures={};details=[]
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        ok,_=im.select("INBOX",readonly=True)
        if ok!="OK":raise RuntimeError("INBOX_UNAVAILABLE")
        def check(r):
            uid_value=str(r.get("uid","")).strip()
            if not re.fullmatch(r"(?:(?i:inbox):)?[0-9]+",uid_value):return "UID_UNUSABLE"
            uid=uid_value.split(":")[-1]
            ok,response=im.uid("FETCH",uid,"(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO DATE FROM SUBJECT)])")
            if ok!="OK":return "IMAP_FETCH_ERROR"
            payload=next((v[1] for v in response or [] if isinstance(v,tuple) and isinstance(v[1],bytes)),None)
            if not payload:return "IMAP_MESSAGE_NOT_FOUND"
            msg=BytesParser(policy=default).parsebytes(payload,headersonly=True)
            from_email={a.lower() for _,a in getaddresses([str(msg.get("From",""))])}
            subject=str(msg.get("Subject","")).strip()
            original={"direction":"INBOUND","from_email":"css@novogene-amea.com" if "css@novogene-amea.com" in from_email else "", "subject":subject,"in_reply_to":str(msg.get("In-Reply-To",""))}
            if not original_issued_mail(original):return "NOT_ORIGINAL_CSS_NOTICE"
            if subject!=str(r.get("subject","")).strip():return "SOURCE_SUBJECT_MISMATCH"
            ok,body_items=im.uid("FETCH",uid,"(BODYSTRUCTURE)")
            if ok!="OK":return "IMAP_BODYSTRUCTURE_FETCH_ERROR"
            raw=[]
            for v in body_items or []:
                if isinstance(v,tuple) and isinstance(v[0],bytes):raw.append(v[0])
                elif isinstance(v,bytes):raw.append(v)
            filenames=[]
            for value in raw:filenames.extend(bodystructure_filenames(value))
            expected=str(r.get("invoice_number","")).strip()
            candidate=[]
            for name in set(filenames):
                parsed=extract(name)
                if parsed and parsed[0]==expected:candidate.append((name,parsed))
            if not candidate:return "ORIGINAL_PDF_FILENAME_UNREADABLE"
            expected_filename=str(r.get("attachment_filename","")).strip()
            for name,p in candidate:
                invoice,h,po,project,amount,status=p
                if (name==expected_filename and h==str(r.get("h_project_number","")).strip()
                    and project==str(r.get("project_id","")).strip()
                    and amount is not None and amount==int(re.sub(r"[^0-9]","",str(r.get("amount_krw","")).split(".")[0]) or "0")):
                    return "ORIGINAL_PDF_AMOUNT_AND_ID_MATCH"
            return "PDF_PROOF_MISMATCH"
        for r in records[:limit]:
            checked+=1
            status=check(r)
            if status=="ORIGINAL_PDF_AMOUNT_AND_ID_MATCH":proof+=1
            else:
                failures[status]=failures.get(status,0)+1
                details.append({"invoice":r.get("invoice_number",""),"status":status})
        im.logout()
    print("QQ_ORIGINAL_INVOICE_PROOF "+json.dumps({"source_rows":len(records),"checked":checked,
       "verified":proof,"failures":failures,"review":details,
       "complete":checked==len(records) and proof==checked,
       "revenue_mutated":False},sort_keys=True))
if __name__=="__main__":main()
