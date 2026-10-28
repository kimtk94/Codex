#!/usr/bin/env python3
"""Sanitized structural probe of IMAP BODYSTRUCTURE; prints no filenames or mail content."""
import imaplib,json,os,re,urllib.parse,base64
from email.header import decode_header,make_header
import incremental_sync as src
from tax_invoice_extract import bodystructure_filenames

def main():
 s=src.authorize()
 p=urllib.parse.quote("'CSS Tax Invoice List'!A1:N7",safe="")
 rows=src.api(s,"GET",src.endpoint("/values/"+p)).get("values",[])
 uids=[]
 for row in rows[1:]:
  if not row:continue
  m=re.fullmatch(r"(?:(?i:inbox):)?([0-9]+)",str(row[12] if len(row)>12 else "").strip())
  if m:u=m.group(1);uids.append(u)
  if len(uids)==5:break
 if not uids:raise RuntimeError("NO_VALID_UIDS")
 with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
  im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
  im.select("INBOX",readonly=True)
  for uid in uids:
   status,items=im.uid("FETCH",uid,"(BODYSTRUCTURE)")
   parts=[]
   for x in items or []:
    if isinstance(x,bytes):parts.append(x)
    elif isinstance(x,tuple):
     if isinstance(x[0],bytes):parts.append(x[0])
     if len(x)>1 and isinstance(x[1],bytes):parts.append(x[1])
   all_bytes=b" ".join(parts)
   literal_bytes=b"".join(parts)
   expected=next((str(row[10]).encode('utf-8') for row in rows[1:] if len(row)>12 and str(row[12]).lower().endswith(uid)),b'')
   tokens=[v.decode("utf-8","replace") for v in re.findall(rb'"([^"]*)"',all_bytes)]
   def indicators(value):
    upper=str(value).upper()
    return "TAX" in upper and "INVOICE" in upper and ".PDF" in upper
   decoded=[]
   for v in tokens:
    try:decoded.append(str(make_header(decode_header(v))))
    except Exception:pass
    try:decoded.append(base64.b64decode(v,validate=True).decode("utf-8","replace"))
    except Exception:pass
   for i in range(len(tokens)):
    for size in range(2,9):
     if i+size>len(tokens):break
     piece="".join(tokens[i:i+size])
     try:decoded.append(str(make_header(decode_header(piece))))
     except Exception:pass
     try:decoded.append(base64.b64decode(piece,validate=True).decode("utf-8","replace"))
     except Exception:pass
   print("IMAP_MIME_SHAPE "+json.dumps({
    "decoded_original_filename_candidate":any(indicators(v) for v in decoded),
    "raw_parts_contain_expected_filename":[bool(expected and expected in v) for v in parts],
    "joined_contains_expected_filename":bool(expected and expected in literal_bytes),
    "expected_filename_length":len(expected),
    "part_tax_tokens":[b"TAX" in v.upper() for v in parts],
    "encoded_word_tokens":sum(v.startswith("=?") for v in tokens),
    "base64_shape_tokens":sum(bool(re.fullmatch(r"[A-Za-z0-9+/=]{20,}",v)) for v in tokens),
    "status":status,"response_types":[type(x).__name__ for x in items or []],
    "byte_lengths":[len(x) for x in parts],
    "contains_bodystructure":b"BODYSTRUCTURE" in all_bytes.upper(),
    "contains_pdf":b"PDF" in all_bytes.upper(),
    "contains_filename_token":b"FILENAME" in all_bytes.upper(),
    "contains_tax_invoice_token":b"TAX" in all_bytes.upper(),
    "quoted_name_candidates":len(bodystructure_filenames(all_bytes)),
    "quote_count":all_bytes.count(b'"'),
    "quoted_token_count":len(re.findall(rb'"([^"]*)"',all_bytes)),
    "quoted_token_lengths":[len(t) for t in re.findall(rb'"([^"]*)"',all_bytes)][:30],
    "percent_sequences":len(re.findall(rb"%[0-9A-Fa-f]{2}",all_bytes)),
    "literal_tax_invoice_pattern":bool(re.search(rb"TAX[ _-]*INVOICE",all_bytes,re.I)),
    "filename_token_position":all_bytes.upper().find(b"FILENAME"),
    "pdf_token_position":all_bytes.upper().find(b"PDF"),
    "paren_count":all_bytes.count(b'(')
   },sort_keys=True))
  im.logout()
if __name__=="__main__":main()
