#!/usr/bin/env python3
"""Read-only tax invoice filename extraction from QQ IMAP BODYSTRUCTURE.

No PDF content is downloaded. No mail is sent or mutated. Only a dedicated
output sheet is written; existing CSS Tax Invoice List/SFDC stay untouched.
"""
import datetime as dt
import imaplib
import os
import re
import sys
import urllib.parse
import incremental_sync as src
import canonical_mail_reader as canonical

TAB="CSS Tax Invoice Extract"
HEADER=["invoice_number","amount_krw","project_id","h_project_number","po_reference",
        "attachment_filename","subject","received_at","imap_uid","ingest_key",
        "validation_status","extracted_at_utc"]
PATTERN=re.compile(
    r"TAX\s+INVOICE[-_ ]+(\d{8,15})[-_ ]+(H\d{5,})[-_ ]+([A-Za-z0-9]+)"
    r"[-_ ]+(AMEA\d{7,}(?:-\d{1,3})?)[-_ ]+KRW\s*([0-9]+(?:\.[0-9]{1,2})?)\.pdf",
    re.I)
ISSUED=re.compile(r"Invoice Issued\s*&\s*Statement Confirmed",re.I)

def read_rows(session,tab,columns,count):
    path=urllib.parse.quote("'"+tab+"'!A1:"+columns+str(count),safe="")
    arr=src.api(session,"GET",src.endpoint("/values/"+path)).get("values",[])
    if not arr:return []
    return [dict(zip(arr[0],r+[""]*(len(arr[0])-len(r)))) for r in arr[1:] if any(r)]

def bodystructure_filenames(message):
    # Parse filenames only from BODYSTRUCTURE metadata, not attachment payloads.
    # Various IMAP servers expose NAME, FILENAME and RFC2231 parameters.
    normalized=re.sub(r"\s+"," ",message.decode("utf-8","replace"))
    strings=re.findall(r'"((?:[^"\\]|\\.)*)"',normalized)
    names=[]
    for raw in strings:
        value=raw.replace(r'\"','"').replace(r'\\','\\')
        if "TAX" in value.upper() and "INVOICE" in value.upper() and ".PDF" in value.upper():
            names.append(value)
    return names

def extract(name):
    cleaned=re.sub(r"\s+"," ",name).strip()
    found=PATTERN.search(cleaned)
    if not found:return None
    invoice,h_project,po,project,value=found.groups()
    # KRW values historically have two decimal positions.
    whole,_,decimal=value.partition(".")
    if decimal and int(decimal)!=0:return (invoice,h_project,po,project,None,"REVIEW_NON_INTEGER_KRW")
    amount=int(whole)
    if amount<=0:return (invoice,h_project,po,project,None,"REVIEW_INVALID_AMOUNT")
    return (invoice,h_project,po,project,amount,"FILENAME_PARSED")

def main():
    session=src.authorize()
    canonical_rows=canonical.read_staging_compatible(session)
    source=[dict(zip(src.COLS,r+[""]*(len(src.COLS)-len(r)))) for r in canonical_rows[1:]]
    existing=read_rows(session,"CSS Tax Invoice List","N",10000)
    previous=read_rows(session,TAB,"L",10000) if TAB in {
        x["properties"]["title"] for x in src.api(session,"GET",src.endpoint()+"?fields=sheets.properties.title").get("sheets",[])
    } else []
    known={str(x.get("invoice_number","")).strip() for x in existing if x.get("invoice_number")}
    output={str(x.get("ingest_key","")):x for x in previous if x.get("ingest_key")}
    # Reconcile known historical invoice evidence before IMAP metadata calls.
    # These are verified earlier by the legacy filename extraction; label provenance.
    legacy_by_uid={str(r.get("uid","")).strip().lower():r for r in existing if r.get("invoice_number")}
    reconciled=0
    for row in source:
        if row.get("direction")!="INBOUND" or row.get("ingest_key") in output:continue
        legacy=legacy_by_uid.get(("inbox:"+str(row.get("imap_uid",""))).lower())
        if not legacy:continue
        amount_text=str(legacy.get("amount_krw","")).replace(",","").replace(" KRW","").strip()
        if not amount_text.isdigit():continue
        key=row["ingest_key"]
        output[key]={"invoice_number":legacy.get("invoice_number",""),
            "amount_krw":int(amount_text),"project_id":legacy.get("project_id",""),
            "h_project_number":legacy.get("h_project_number",""),
            "po_reference":legacy.get("po_reference",""),
            "attachment_filename":legacy.get("attachment_filename",""),
            "subject":row.get("subject",""),"received_at":row.get("received_at",""),
            "imap_uid":row.get("imap_uid",""),"ingest_key":key,
            "validation_status":"VERIFIED_LEGACY_RECORD",
            "extracted_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
        reconciled+=1
    candidates=[x for x in source if x.get("direction")=="INBOUND" and
                ISSUED.search(str(x.get("subject",""))) and x.get("ingest_key") not in output]
    # Newest first; per-run bound avoids exceeding the 10-minute Actions job.
    candidates.sort(key=lambda x:x.get("received_at",""),reverse=True)
    batch=candidates[:int(os.environ.get("CSS_INVOICE_BATCH","120"))]
    if batch:
        with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
            im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
            status,_=im.select("INBOX",readonly=True)
            if status!="OK":raise RuntimeError("Invoice INBOX select failed")
            status,uv=im.response("UIDVALIDITY")
            current=(uv[0] or b"").decode() if uv else ""
            for row in batch:
                key=row["ingest_key"]
                if row.get("uidvalidity")!=current:
                    continue
                status,items=im.uid("FETCH",row["imap_uid"],"(BODYSTRUCTURE)")
                if status!="OK":raise RuntimeError("Invoice BODYSTRUCTURE fetch failed")
                structures=[v for v in items or [] if isinstance(v,bytes)]
                structures += [v[0] for v in items or [] if isinstance(v,tuple) and isinstance(v[0],bytes)]
                names=[]
                for item in structures:names+=bodystructure_filenames(item)
                results=[(name,extract(name)) for name in names]
                results=[(name,p) for name,p in results if p]
                if not results:
                    # Keep retryable: filename metadata format may differ by server.
                    continue
                name,parsed=results[0]
                invoice,h_project,po,project,amount,status=parsed
                if invoice in known:status="EXISTS_IN_LEGACY"
                output[key]={"invoice_number":invoice,"amount_krw":amount if amount is not None else "",
                             "project_id":project,"h_project_number":h_project,"po_reference":po,
                             "attachment_filename":name,"subject":row["subject"],"received_at":row["received_at"],
                             "imap_uid":row["imap_uid"],"ingest_key":key,"validation_status":status,
                             "extracted_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
            im.logout()
    metadata=src.api(session,"GET",src.endpoint()+"?fields=sheets.properties.title")
    if TAB not in {v["properties"]["title"] for v in metadata.get("sheets",[])}:
        src.api(session,"POST",src.endpoint(":batchUpdate"),
                json={"requests":[{"addSheet":{"properties":{"title":TAB,"gridProperties":{"frozenRowCount":1}}}}]})
    values=[HEADER]+[[x.get(column,"") for column in HEADER] for x in output.values()]
    if len(values)>10000:raise RuntimeError("Invoice output exceeds safe sheet range")
    def rng(cell):return urllib.parse.quote("'"+TAB+"'!"+cell,safe="")
    src.api(session,"POST",src.endpoint("/values/"+rng("A1:L10000")+":clear"),json={})
    src.api(session,"PUT",src.endpoint("/values/"+rng("A1"))+"?valueInputOption=RAW",
            json={"values":values})
    print("CSS_INVOICE_PASS candidates="+str(len(candidates))+" fetched="+str(len(batch))+
          " extracted_total="+str(len(output))+" reconciled_legacy="+str(reconciled)+" filename_only=true")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("CSS_INVOICE_FAILED "+(str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)
