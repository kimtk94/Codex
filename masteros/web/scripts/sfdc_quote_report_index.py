"""Offline Salesforce Quotation Report index (EUC-KR HTML disguised as .xls).

Indexes the user's *previously exported* reports. A contact's actual discount,
price, quantity and quote belong to that report line only. Shared process
definitions are stored once by canonical Process ID + name + Data Unit.

The report contains USD *converted* figures, not a verified KRW quote rate.
This module NEVER asserts current Salesforce availability, creates quotes, or
promotes report USD into the live KRW price gate. No network/UI calls.
"""
from __future__ import annotations
from collections import Counter
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

DB_DIR=Path.home()/".sfdc_desktop"
DB_PATH=DB_DIR/"sfdc_quote_report_index_PRIVATE.sqlite3"
ALLOWED_DOWNLOADS=Path.home()/"Downloads"
LINE_PREFIX="Automation   Quotation-"
HEADER_PREFIX="Automation   Quotation Report-"
LINE_FIELDS=("SFDC Quotation ID","Quotation Product ID","Contact ID","Opportunity ID",
 "Total Price USD (converted) Currency","Total Price USD (converted)",
 "Sales Price USD (converted)","Unit Price USD","Quotation Process Name",
 "Process Name: SFDC Process ID","Quote Process Name","Created Date",
 "Data Unit","Sample Quantity","Data Size")
HEAD_FIELDS=("Quotation: SFDC Quotation ID","Quotation: ID","Opportunity ID",
 "Contact ID","Account Name","Quotation Name","Exclude Tax After Discount USD")
SFDC_ID=re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
QUOTE_ID=re.compile(r"^QID-[0-9-]{8,40}$")
MAX_HTML_BYTES=100000000


class ReportError(ValueError):
    pass


class TableReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.row=[];self.fragments=[];self.in_cell=False
    def handle_starttag(self,tag,attrs):
        if tag in ("td","th"):
            self.in_cell=True
            self.fragments=[]
    def handle_data(self,data):
        if self.in_cell:self.fragments.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th"):
            self.row.append("".join(self.fragments).strip())
            self.in_cell=False
        elif tag=="tr" and self.row:
            self.rows.append(self.row)
            self.row=[]


def read_export(path,required):
    if not path.is_file() or path.stat().st_size>MAX_HTML_BYTES:
        raise ReportError("REPORT_FILE_UNAVAILABLE")
    data=path.read_bytes()
    if not data.lstrip().lower().startswith(b"<head>"):
        raise ReportError("NOT_SFDC_HTML_EXPORT")
    charset="euc-kr" if b"charset=euc-kr" in data[:350].lower() else "utf-8"
    t=TableReader()
    t.feed(data.decode(charset,errors="strict"))
    if len(t.rows)<2:
        raise ReportError("REPORT_EMPTY")
    headers=t.rows[0]
    if len(set(headers))!=len(headers):
        raise ReportError("REPORT_DUPLICATE_HEADERS")
    if not all(k in headers for k in required):
        raise ReportError("REPORT_REQUIRED_HEADERS_MISSING")
    if any(len(row)!=len(headers) for row in t.rows[1:]):
        raise ReportError("REPORT_ROW_WIDTH_MISMATCH")
    return [dict(zip(headers,row)) for row in t.rows[1:]],hashlib.sha256(data).hexdigest()


def _find_files(folder):
    folder=Path(folder)
    if folder.resolve()!=ALLOWED_DOWNLOADS.resolve():
        raise ReportError("REPORT_DIRECTORY_NOT_ALLOWED")
    files=[p for p in folder.glob("Automation*Quotation*.xls") if p.is_file()]
    lines=sorted([p for p in files if p.name.startswith(LINE_PREFIX)],
                 key=lambda p:(p.stat().st_mtime,p.name),reverse=True)
    headers=sorted([p for p in files if p.name.startswith(HEADER_PREFIX)],
                   key=lambda p:(p.stat().st_mtime,p.name),reverse=True)
    if not lines or not headers:
        raise ReportError("REPORT_PAIR_NOT_FOUND")
    # Select the newest matching *full* 25-column process report rather than
    # an older 22-column or ambiguous 27-column intermediate export.
    valid=[]
    for path in lines:
        try:
            rows,sha=read_export(path,LINE_FIELDS)
            valid.append((path,rows,sha))
            break
        except (ReportError,UnicodeDecodeError):
            continue
    if not valid:
        raise ReportError("REPORT_PROCESS_FILE_NOT_VALID")
    header_path=headers[0]
    headrows,headsha=read_export(header_path,HEAD_FIELDS)
    if abs(lines[0].stat().st_mtime-header_path.stat().st_mtime)>7*86400:
        raise ReportError("REPORT_PAIR_EXPORT_DATES_DIFFER")
    return (*valid[0],header_path,headrows,headsha)


def decimal_text(value):
    value=(value or "").strip().replace(",","")
    if value.lower() in ("","null","-"):
        return None
    try:
        decimal=Decimal(value)
    except InvalidOperation:
        raise ReportError("REPORT_NON_NUMERIC_AMOUNT")
    if not decimal.is_finite() or abs(decimal)>Decimal("999999999999"):
        raise ReportError("REPORT_INVALID_AMOUNT")
    return str(decimal)


def _connection(path):
    cx=sqlite3.connect(str(path),timeout=10)
    cx.execute("PRAGMA foreign_keys=ON")
    return cx


def import_reports(folder=ALLOWED_DOWNLOADS):
    path,lines,sha,head_path,heads,headsha=_find_files(folder)
    by_business={}
    for row in heads:
        qid=row["Quotation: SFDC Quotation ID"]
        rid=row["Quotation: ID"]
        if not QUOTE_ID.fullmatch(qid) or not SFDC_ID.fullmatch(rid):
            raise ReportError("REPORT_QUOTE_ID_INVALID")
        if qid in by_business:
            raise ReportError("REPORT_HEADER_QUOTE_DUPLICATED")
        by_business[qid]=row
    # Check 100% quote-identity mapping before replacing the existing index.
    quote_ids={r["SFDC Quotation ID"] for r in lines}
    if not quote_ids or quote_ids.difference(by_business):
        raise ReportError("REPORT_QUOTE_LINKAGE_INCOMPLETE")

    DB_DIR.mkdir(parents=True,exist_ok=True)
    if os.name!="nt":os.chmod(DB_DIR,0o700)
    staging=DB_DIR/"sfdc_quote_report_stage_PRIVATE.sqlite3"
    if staging.exists():
        # Staging is this module's own temporary file only.
        staging.unlink()
    cx=_connection(staging)
    try:
        with cx:
            cx.executescript("""CREATE TABLE metadata(k TEXT PRIMARY KEY,v TEXT NOT NULL);
            CREATE TABLE quote_headers(
                business_quote_id TEXT PRIMARY KEY,
                salesforce_record_id TEXT NOT NULL UNIQUE,
                account_name TEXT, contact_name TEXT, contact_id TEXT,
                opportunity_external_id TEXT, quotation_name TEXT,
                active TEXT, created_date TEXT,
                quote_ex_tax_usd TEXT);
            CREATE TABLE process_dictionary(
                definition_hash TEXT PRIMARY KEY,process_id TEXT NOT NULL,
                process_name TEXT NOT NULL,data_unit TEXT NOT NULL);
            CREATE TABLE quote_process_lines(
                row_number INTEGER PRIMARY KEY, business_quote_id TEXT NOT NULL,
                quotation_product_id TEXT NOT NULL,
                definition_hash TEXT NOT NULL,
                unit_price_usd TEXT, sales_price_usd TEXT,
                product_total_usd TEXT, sample_quantity TEXT, data_size TEXT,
                created_date TEXT, active TEXT,
                FOREIGN KEY(business_quote_id) REFERENCES quote_headers(business_quote_id),
                FOREIGN KEY(definition_hash) REFERENCES process_dictionary(definition_hash));
            CREATE INDEX ix_quote_process_lines_quote ON quote_process_lines(business_quote_id);
            CREATE INDEX ix_quote_product_id ON quote_process_lines(quotation_product_id);
            CREATE INDEX ix_process_reference ON quote_process_lines(definition_hash);
            CREATE INDEX ix_quote_header_recid ON quote_headers(salesforce_record_id);
            """)
            newest=None
            for row in heads:
                qid=row["Quotation: SFDC Quotation ID"]
                if qid not in quote_ids:
                    continue
                cx.execute("""INSERT INTO quote_headers VALUES(?,?,?,?,?,?,?,?,?,?)""",(
                    qid,row["Quotation: ID"],row.get("Account Name",""),
                    row.get("Contact Name",""),row.get("Contact ID",""),
                    row.get("Opportunity ID",""),row.get("Quotation Name",""),
                    row.get("Active",""),row.get("Quotation Create Date",""),
                    decimal_text(row.get("Exclude Tax After Discount USD"))))
            process_templates={}
            for i,row in enumerate(lines,1):
                qid=row["SFDC Quotation ID"]
                pid=row["Process Name: SFDC Process ID"]
                proc=row["Quote Process Name"]
                unit=row["Data Unit"]
                if not pid or not proc:
                    raise ReportError("REPORT_PROCESS_STRUCTURE_MISSING")
                if row["Total Price USD (converted) Currency"]!="USD":
                    raise ReportError("UNEXPECTED_REPORT_CURRENCY")
                canonical=(pid,proc,unit)
                structural_id=hashlib.sha256(json.dumps(
                    canonical,ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
                process_templates[structural_id]=canonical
                # Foreign key must exist before the per-Quote price row.
                cx.execute("""INSERT OR IGNORE INTO process_dictionary
                    VALUES(?,?,?,?)""",(structural_id,*canonical))
                raw_date=row["Created Date"].strip()
                when=dt.datetime.strptime(raw_date,"%m/%d/%Y").date()
                if newest is None or when>newest:newest=when
                cx.execute("""INSERT INTO quote_process_lines VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
                    i,qid,row["Quotation Product ID"],structural_id,
                    decimal_text(row["Unit Price USD"]),
                    decimal_text(row["Sales Price USD (converted)"]),
                    decimal_text(row["Total Price USD (converted)"]),
                    decimal_text(row["Sample Quantity"]),
                    decimal_text(row["Data Size"]),when.isoformat(),row.get("Active","")))
            meta={
                "source":"LOCAL_SFDC_REPORT_HTML_EXPORT",
                "line_file":path.name,"line_sha256":sha,
                "header_file":head_path.name,"header_sha256":headsha,
                "file_exported_utc":dt.datetime.fromtimestamp(
                    path.stat().st_mtime,dt.timezone.utc).isoformat(timespec="seconds"),
                "max_created_date":newest.isoformat() if newest else "",
                "ingested_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "quote_count":str(len(quote_ids)),"line_count":str(len(lines)),
                "quote_products":str(len({r["Quotation Product ID"] for r in lines})),
                "process_definitions":str(len(process_templates)),
                "currency":"USD_CONVERTED_ONLY",
                "live_sfdc_verified":"false",
            }
            cx.executemany("INSERT INTO metadata VALUES(?,?)",meta.items())
    finally:
        cx.close()
    if os.name!="nt":os.chmod(staging,0o600)
    os.replace(staging,DB_PATH)
    return status()


def _read():
    if not DB_PATH.is_file():
        raise ReportError("REPORT_NOT_INDEXED")
    return _connection(DB_PATH)


def _meta(cx):
    return dict(cx.execute("SELECT k,v FROM metadata").fetchall())


def status():
    try:
        cx=_read()
        try:
            meta=_meta(cx)
            exported=dt.datetime.fromisoformat(meta["file_exported_utc"])
            age=(dt.datetime.now(dt.timezone.utc)-exported).total_seconds()
            return {"status":"PASS","source_state":"STALE" if age>86400 else "REPORT_SNAPSHOT",
                "quote_count":int(meta["quote_count"]),
                "process_rows":int(meta["line_count"]),
                "product_count":int(meta["quote_products"]),
                "unique_process_definitions":int(meta["process_definitions"]),
                "process_references":int(meta["line_count"]),
                "snapshot_exported_at_utc":meta["file_exported_utc"],
                "newest_quote_created_date":meta["max_created_date"],
                "ingested_at_utc":meta["ingested_at_utc"],
                "currency":"USD_CONVERTED_ONLY",
                "krw_rate_verified":False,"salesforce_write":False,
                "local_only":True}
        finally:cx.close()
    except (OSError,sqlite3.DatabaseError,KeyError,ValueError,ReportError):
        return {"status":"BLOCK","code":"REPORT_INDEX_NOT_AVAILABLE",
                "local_only":True,"salesforce_write":False}


def search(query="",limit=25):
    if not isinstance(query,str) or len(query)>80 or not isinstance(limit,int) or not 1<=limit<=30:
        raise ReportError("REPORT_SEARCH_INVALID")
    cx=_read()
    try:
        s=f"%{query}%"
        rows=cx.execute("""SELECT q.business_quote_id,q.salesforce_record_id,
            q.account_name,q.contact_name,q.quotation_name,q.created_date,
            q.active,COUNT(DISTINCT l.quotation_product_id),
            COUNT(l.row_number)
            FROM quote_headers q JOIN quote_process_lines l
            ON l.business_quote_id=q.business_quote_id
            JOIN process_dictionary d ON d.definition_hash=l.definition_hash
            WHERE q.business_quote_id LIKE ? OR q.account_name LIKE ?
               OR q.contact_name LIKE ? OR q.quotation_name LIKE ?
               OR d.process_name LIKE ?
            GROUP BY q.business_quote_id
            ORDER BY q.created_date DESC,q.business_quote_id DESC LIMIT ?""",
            (s,s,s,s,s,limit)).fetchall()
        return {"status":"PASS","source_state":"HISTORICAL_REPORT",
            "rows":[{"qid":r[0],"sfdc_record_id":r[1],
                "account_name":r[2],"contact_name":r[3],
                "quote_name":r[4],"created_date":r[5],
                "active":r[6]=="1","product_count":r[7],
                "process_lines":r[8]} for r in rows],
            "currency":"USD_CONVERTED_ONLY","krw_rate_verified":False,
            "salesforce_write":False,"local_only":True}
    finally:cx.close()


def detail(identifier):
    if not isinstance(identifier,str) or len(identifier)>60 or not (
            QUOTE_ID.fullmatch(identifier) or SFDC_ID.fullmatch(identifier)):
        raise ReportError("REPORT_QUOTE_IDENTIFIER_INVALID")
    cx=_read()
    try:
        if identifier.startswith("a0P"):
            # 15-character Salesforce report ID vs newer 18-character UI ID.
            rows=cx.execute("""SELECT business_quote_id FROM quote_headers
                WHERE salesforce_record_id=?""",(identifier[:15],)).fetchall()
            if len(rows)!=1:
                raise ReportError("REPORT_SFDC_ID_NOT_UNIQUE")
            qid=rows[0][0]
        else:
            qid=identifier
        q=cx.execute("""SELECT business_quote_id,salesforce_record_id,
            account_name,contact_name,quotation_name,active,created_date,
            quote_ex_tax_usd FROM quote_headers WHERE business_quote_id=?""",
            (qid,)).fetchone()
        if not q:raise ReportError("REPORT_QUOTE_NOT_FOUND")
        lines=cx.execute("""SELECT l.quotation_product_id,d.process_id,
            d.process_name,d.data_unit,l.unit_price_usd,l.sales_price_usd,
            l.product_total_usd,l.sample_quantity,l.data_size
            FROM quote_process_lines l JOIN process_dictionary d
                ON d.definition_hash=l.definition_hash
            WHERE l.business_quote_id=? ORDER BY l.row_number LIMIT 121""",
            (qid,)).fetchall()
        if len(lines)>120:
            raise ReportError("REPORT_LINE_LIMIT_EXCEEDED")
        return {"status":"PASS","source_state":"HISTORICAL_REPORT",
            "qid":q[0],"sfdc_record_id":q[1],
            "account_name":q[2],"contact_name":q[3],
            "quote_name":q[4],"active":q[5]=="1",
            "created_date":q[6],"quote_ex_tax_usd_report":q[7],
            "product_count":len({l[0] for l in lines}),
            "process_lines":[{"quotation_product_id":l[0],
                "process_id":l[1],"process_name":l[2],
                "data_unit":l[3],"unit_price_usd":l[4],
                "sales_price_usd_converted":l[5],
                "product_total_usd_converted":l[6],
                "sample_quantity":l[7],"data_size":l[8]}
                for l in lines],
            "currency":"USD_CONVERTED_ONLY","krw_rate_verified":False,
            "salesforce_write":False,"local_only":True}
    finally:cx.close()


def run(request):
    if not isinstance(request,dict):raise ReportError("REPORT_REQUEST_INVALID")
    mode=request.get("mode")
    if mode=="IMPORT":return import_reports()
    # Google Sheet is the newer persisted *Report*, not a live Salesforce
    # read. Keep the older local HTML .xls only as a fallback/ID bridge.
    from sfdc_quote_report_sheet import status as sheet_status
    from sfdc_quote_report_sheet import search as sheet_search
    from sfdc_quote_report_sheet import detail as sheet_detail
    from sfdc_quote_report_sheet import sync_staged
    if mode=="SYNC_STAGED":return sync_staged()
    if mode=="STATUS":
        current=sheet_status()
        return current if current.get("status")=="PASS" else status()
    if mode=="SEARCH":
        if sheet_status().get("status")=="PASS":
            return sheet_search(request.get("query",""),request.get("limit",25))
        return search(request.get("query",""),request.get("limit",25))
    if mode=="DETAIL":
        if sheet_status().get("status")=="PASS":
            try:
                return sheet_detail(request.get("id"))
            except ReportError as exc:
                if str(exc) not in ("SHEET_SFDC_ID_UNMAPPED","SHEET_QUOTE_NOT_FOUND"):
                    raise
        return detail(request.get("id"))
    raise ReportError("REPORT_MODE_NOT_ALLOWED")


if __name__=="__main__":
    try:
        data=sys.stdin.buffer.read(1024)
        if not data or len(data)>=1024:raise ReportError("REPORT_REQUEST_TOO_LARGE")
        res=run(json.loads(data.decode("utf-8")))
    except (ReportError,ValueError,UnicodeError,TypeError,sqlite3.DatabaseError):
        res={"status":"BLOCK","code":"REPORT_INPUT_OR_SOURCE_INVALID",
             "salesforce_write":False,"local_only":True}
    except Exception:
        res={"status":"BLOCK","code":"REPORT_INDEX_UNAVAILABLE",
             "salesforce_write":False,"local_only":True}
    print(json.dumps(res,ensure_ascii=False,separators=(",",":")))
