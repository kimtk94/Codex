#!/usr/bin/env python3
"""Read-only semantic audit of Feishu original eTax Tracking file column H.

This distinguishes an actual eTax issuance status from a hyperlink, document
reference, notes, unrecognized text, or a formula value. No confidential
raw H values or other row fields are logged publicly. No Sheet writes.
"""
import re
import sys
import urllib.parse

from qq_mail_ingest import api,SafeError,auth
from etax_original_tracking_proof import (
    TRACKING_TOKEN,TRACKING_TAB,TARGETS,read_tracking,build_index,
    scalar,classify_status,
)

INTERESTING=("20910000203","20910000208","20910000209",
             "20910000197","209126001032","209126000926",
             "209126000984")
HEADER_COLUMNS=(3,4,6,7,8,9,10,11)
PDF_TOKENS=("PDF",".PDF","发票文件","첨부","ATTACHMENT")
ISSUANCE_TOKENS=("已开票","已开具","开票成功","발행 완료","ISSUED","发票已","전자세금계산서")
PENDING_TOKENS=("未开票","未开","待开","未生成","미발행","NOT ISSUED","CANCEL","待确认")
HYPERLINK_TOKENS=("HTTP://","HTTPS://","HYPERLINK(","LARK.COM","FEISHU.CN","FILE://","DRIVE.")
HEADER_OK=re.compile(r"^[A-Za-z\u3400-\u9fff\uac00-\ud7af\u3040-\u30ff \-_:()/?+&.#]{1,60}$")


def safe_header(value):
    raw=scalar(value)
    # Header names are metadata and only log safe alphabetic column labels,
    # not potentially identifying raw invoice data or URLs.
    return raw if HEADER_OK.fullmatch(raw) and not any(
        tok in raw.upper() for tok in HYPERLINK_TOKENS) else "HEADER_NOT_CLASSIFIABLE"


def signals(value):
    text=scalar(value)
    upper=text.upper()
    markers=[]
    if any(tok in upper for tok in HYPERLINK_TOKENS):markers.append("URL_OR_LINK")
    if any(tok in upper for tok in PDF_TOKENS):markers.append("PDF_OR_FILE")
    if any(tok in upper for tok in ISSUANCE_TOKENS):markers.append("ISSUANCE_WORD")
    if any(tok in upper for tok in PENDING_TOKENS):markers.append("NEGATIVE_OR_PENDING_WORD")
    if re.search(r"20\d{2}[-./]\d\d?[-./]\d\d?",text):markers.append("DATE_STRING")
    if re.search(r"\b\d{8,}\b",text):markers.append("EMBEDDED_LONG_NUMBER")
    if re.search(r"[\u3400-\u9fff]",text):markers.append("CHINESE_TEXT")
    if re.search(r"[\uac00-\ud7af]",text):markers.append("KOREAN_TEXT")
    if re.search(r"[A-Za-z]",text):markers.append("LATIN_TEXT")
    if not markers:markers.append("OPAQUE_TEXT")
    return markers


def cell_data(value):
    raw=scalar(value)
    kind=("rich_dict" if isinstance(value,dict) else
          "rich_list" if isinstance(value,list) else
          "empty" if not raw else "plain_"+type(value).__name__)
    return {"kind":kind,"length":len(raw),"signals":signals(value),
            "classification":classify_status(value)}


def row_read(token,sheet_id,first,last):
    path=(f"/open-apis/sheets/v2/spreadsheets/"
          f"{urllib.parse.quote(TRACKING_TOKEN,safe='')}/values/"
          f"{urllib.parse.quote(f'{sheet_id}!A{first}:N{last}',safe='')}")
    d=api("GET",path,token,action="original_etax_tracking_semantic_probe")
    vr=d.get("valueRange")
    if not isinstance(vr,dict) or not isinstance(vr.get("values"),list):
        raise SafeError("ETAX_SEMANTIC_RANGE_INVALID")
    rows=vr["values"]
    if len(rows)>last-first+1:
        raise SafeError("ETAX_SEMANTIC_RANGE_OVERFLOW")
    return rows


def find_sheet(token):
    path=f"/open-apis/sheets/v3/spreadsheets/{urllib.parse.quote(TRACKING_TOKEN,safe='')}/sheets/query"
    d=api("GET",path,token,action="etax_tracking_semantics_sheet_catalog")
    sheets=[x for x in d.get("sheets") or [] if x.get("title")==TRACKING_TAB]
    if len(sheets)!=1 or not sheets[0].get("sheet_id"):
        raise SafeError("ETAX_SEMANTIC_SHEET_NOT_FOUND")
    return sheets[0]["sheet_id"]


def audit(token):
    full,rev=read_tracking(token)
    index=build_index(full)
    if not full:raise SafeError("ETAX_SEMANTIC_SOURCE_EMPTY")
    sid=find_sheet(token)
    heads=row_read(token,sid,1,1)
    row=heads[0] if heads else []
    for i in HEADER_COLUMNS:
        col=chr(ord("A")+i)
        h=safe_header(row[i] if len(row)>i else "")
        print("ETAX_SEMANTIC_HEADER col="+col+" label="+h,flush=True)
    resolved=0
    for invoice in INTERESTING:
        status,line=index.get(invoice,("",0))
        if not line:
            print("ETAX_SEMANTIC invoice="+invoice+" evidence=NOT_IN_ORIGINAL_"+
                  "TRACKING_750_ROWS owner_and_issuance=UNPROVEN",flush=True)
            continue
        records=row_read(token,sid,line,line)
        if len(records)!=1 or len(records[0])<=7:
            raise SafeError("ETAX_SEMANTIC_TARGET_ROW_INCOMPLETE")
        r=records[0]
        if scalar(r[3])!=invoice or scalar(r[7])!=status:
            raise SafeError("ETAX_SEMANTIC_ID_OR_H_VALUE_CHANGED_DURING_AUDIT")
        h=cell_data(r[7])
        g=cell_data(r[6] if len(r)>6 else "")
        i=cell_data(r[8] if len(r)>8 else "")
        # The metadata column header H, not the user's mirrored formula,
        # determines whether H represents a status, a file or a date.
        print("ETAX_SEMANTIC invoice="+invoice+
              " row="+str(line)+
              " H_class="+h["classification"]+
              " H_kind="+h["kind"]+
              " H_signals="+",".join(h["signals"])+
              " H_length="+str(h["length"])+
              " G_signals="+",".join(g["signals"])+
              " I_signals="+",".join(i["signals"])+
              " raw_values_logged=NO",flush=True)
        resolved+=1
    print("ETAX_SEMANTIC_AUDIT_PASS indexed="+str(len(index))+
          " checked="+str(len(INTERESTING))+
          " original_rows="+str(len(full))+
          " target_rows_found="+str(resolved)+
          " original_revision_present="+str(rev is not None)+
          " sheet_writes=0 revenue_writes=0",flush=True)


if __name__=="__main__":
    try:
        token,_=auth()
        audit(token)
    except Exception as exc:
        err=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("ETAX_SEMANTIC_AUDIT_FAILED="+err,file=sys.stderr)
        sys.exit(1)
