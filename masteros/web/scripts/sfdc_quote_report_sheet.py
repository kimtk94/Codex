"""Local cached index of the *already collected* SFDC Email Quotation Raw sheet.

Input is a private, bounded JSON chunk snapshot delivered by the connected
Google Drive source. No Salesforce browser/UI, user credentials, or network.
The Quote/Product/Process hierarchy is kept separate; converted USD prices
are never promoted to original KRW prices.
"""
from __future__ import annotations
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3

from sfdc_quote_report_index import (
    DB_DIR,DB_PATH,QUOTE_ID,SFDC_ID,ReportError,decimal_text,
    _connection
)

STAGING=DB_DIR/"quote_report_sheet_sync"
SHEET_DB=DB_DIR/"sfdc_quote_sheet_index_PRIVATE.sqlite3"
SHEET_ID="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
HEADER=("SFDC Quotation ID","Quotation Product ID",
 "Contact Name: Full Name","Contact ID","Email",
 "Opportunity Name: Opportunity Name","Opportunity ID",
 "Account Name: Account Name","*Account Id",
 "Active","Sync CMS","Opportunity Amount USD",
 "Total Price USD (converted) Currency","Total Price USD (converted)",
 "Sales Price USD (converted) Currency","Sales Price USD (converted)",
 "Unit Price USD","Quotation Process Name",
 "Process Name: SFDC Process ID","Quote Process Name","Created Date",
 "Quotation PDF Created Time","Data Unit","Sample Quantity","Data Size")


def load_staged_chunks(folder=None):
    folder=Path(STAGING if folder is None else folder)
    if folder.resolve()!=STAGING.resolve():
        raise ReportError("UNEXPECTED_SHEET_STAGE")
    parts=sorted(folder.glob("part_*.json"))
    if not parts:
        raise ReportError("SHEET_REPORT_NOT_STAGED")
    first=2
    rows=[]
    hashes=[]
    for path in parts:
        value=path.read_bytes()
        if len(value)>900000:raise ReportError("SHEET_PART_TOO_LARGE")
        payload=json.loads(value.decode("utf-8"))
        if (not isinstance(payload,dict) or payload.get("source")!="SFDC_Email_Quotation_Raw"
            or payload.get("sheet_id")!=SHEET_ID
            or payload.get("first_row")!=first
            or not isinstance(payload.get("rows"),list)
            or payload.get("last_row")!=first+len(payload["rows"])-1):
            raise ReportError("SHEET_PART_SEQUENCE_INVALID")
        for row in payload["rows"]:
            if not isinstance(row,list) or len(row)>len(HEADER):
                raise ReportError("SHEET_ROW_INVALID")
            rows.append({key:(str(row[index]) if index<len(row) and row[index] is not None else "")
                         for index,key in enumerate(HEADER)})
        first=payload["last_row"]+1
        hashes.append(hashlib.sha256(value).hexdigest())
    if not rows:raise ReportError("SHEET_REPORT_EMPTY")
    return rows,hashlib.sha256("".join(hashes).encode("ascii")).hexdigest()


def _identity_map():
    if not DB_PATH.is_file():return {}
    cx=_connection(DB_PATH)
    try:
        return dict(cx.execute("""SELECT business_quote_id,salesforce_record_id
            FROM quote_headers""").fetchall())
    finally:cx.close()


def _date(value):
    raw=str(value or "").strip()
    try:
        return dt.datetime.strptime(raw,"%m/%d/%Y").date().isoformat()
    except ValueError:
        raise ReportError("SHEET_CREATED_DATE_INVALID")


def sync_staged():
    rows,digest=load_staged_chunks()
    identity=_identity_map()
    DB_DIR.mkdir(parents=True,exist_ok=True)
    stage=DB_DIR/"sfdc_quote_sheet_stage_PRIVATE.sqlite3"
    if stage.exists():stage.unlink()
    cx=_connection(stage)
    try:
        with cx:
            cx.executescript("""CREATE TABLE metadata(k TEXT PRIMARY KEY,v TEXT NOT NULL);
            CREATE TABLE quote_headers(
                business_quote_id TEXT PRIMARY KEY,
                salesforce_record_id TEXT UNIQUE,
                contact_name TEXT,contact_id TEXT,
                account_name TEXT,opportunity_name TEXT,
                opportunity_external_id TEXT,created_date TEXT,active TEXT);
            CREATE TABLE process_dictionary(
                definition_hash TEXT PRIMARY KEY,
                process_id TEXT NOT NULL,
                process_name TEXT NOT NULL,data_unit TEXT NOT NULL);
            CREATE TABLE quote_process_lines(
                row_number INTEGER PRIMARY KEY,
                business_quote_id TEXT NOT NULL,
                quotation_product_id TEXT NOT NULL,
                definition_hash TEXT NOT NULL,
                unit_price_usd TEXT,sales_price_usd TEXT,
                product_total_usd TEXT,sample_quantity TEXT,
                data_size TEXT,created_date TEXT,active TEXT,
                FOREIGN KEY(business_quote_id) REFERENCES quote_headers(business_quote_id),
                FOREIGN KEY(definition_hash) REFERENCES process_dictionary(definition_hash));
            CREATE INDEX ix_sheet_quote ON quote_process_lines(business_quote_id);
            CREATE INDEX ix_sheet_process ON quote_process_lines(definition_hash);
            CREATE INDEX ix_sheet_record_id ON quote_headers(salesforce_record_id);""")
            process_types=set()
            quote_products=set()
            latest=None
            quote_map={}
            normalized=[]
            for ordinal,r in enumerate(rows,1):
                qid=r["SFDC Quotation ID"]
                product=r["Quotation Product ID"]
                procid=r["Process Name: SFDC Process ID"]
                procname=r["Quote Process Name"]
                currency=r["Total Price USD (converted) Currency"]
                if not QUOTE_ID.fullmatch(qid) or not product or not procid or not procname:
                    raise ReportError("SHEET_QUOTE_PROCESS_ID_INVALID")
                if currency!="USD" or r["Sales Price USD (converted) Currency"]!="USD":
                    raise ReportError("SHEET_CURRENCY_NOT_USD")
                date=_date(r["Created Date"])
                if latest is None or latest<date:latest=date
                definition=(procid,procname,r["Data Unit"])
                fingerprint=hashlib.sha256(json.dumps(definition,
                    ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
                process_types.add(fingerprint)
                quote_products.add((qid,product))
                header=(qid,identity.get(qid),
                        r["Contact Name: Full Name"],r["Contact ID"],
                        r["Account Name: Account Name"],
                        r["Opportunity Name: Opportunity Name"],
                        r["Opportunity ID"],date,r["Active"])
                existing=quote_map.get(qid)
                if existing:
                    # Quote row may repeat by process, but identities must agree.
                    if existing[:7]!=header[:7]:
                        raise ReportError("SHEET_QUOTE_HEADER_CONFLICT")
                    if date>existing[7]:
                        header=existing[:7]+(date,existing[8])
                    else:
                        header=existing
                quote_map[qid]=header
                normalized.append((ordinal,qid,product,fingerprint,
                    decimal_text(r["Unit Price USD"]),
                    decimal_text(r["Sales Price USD (converted)"]),
                    decimal_text(r["Total Price USD (converted)"]),
                    decimal_text(r["Sample Quantity"]),
                    decimal_text(r["Data Size"]),date,r["Active"],definition))
            for row in quote_map.values():
                cx.execute("INSERT INTO quote_headers VALUES(?,?,?,?,?,?,?,?,?)",row)
            for value in normalized:
                ordinal,qid,product,key,unit,sales,total,qty,size,date,active,definition=value
                cx.execute("INSERT OR IGNORE INTO process_dictionary VALUES(?,?,?,?)",
                           (key,*definition))
                cx.execute("INSERT INTO quote_process_lines VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (ordinal,qid,product,key,unit,sales,total,qty,size,date,active))
            meta={
                "source":"GOOGLE_SHEET_SFDC_EMAIL_QUOTATION_RAW",
                "sheet_id":SHEET_ID,"tab":"SFDC Email Quotation Raw",
                "snapshot_digest_sha256":digest,
                "ingested_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "max_created_date":latest or "",
                "quote_count":str(len(quote_map)),"line_count":str(len(rows)),
                "quote_products":str(len(quote_products)),
                "process_definitions":str(len(process_types)),
                "linked_sfdc_ids":str(sum(bool(x[1]) for x in quote_map.values())),
                "currency":"USD_CONVERTED_ONLY",
                "live_sfdc_verified":"false",
            }
            cx.executemany("INSERT INTO metadata VALUES(?,?)",meta.items())
    finally:
        cx.close()
    if os.name!="nt":os.chmod(stage,0o600)
    os.replace(stage,SHEET_DB)
    return status()


def _read():
    if not SHEET_DB.is_file():
        raise ReportError("SHEET_REPORT_NOT_INDEXED")
    return _connection(SHEET_DB)


def status():
    try:
        cx=_read()
        try:
            meta=dict(cx.execute("SELECT k,v FROM metadata").fetchall())
            most_recent=dt.date.fromisoformat(meta["max_created_date"])
            age_days=(dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
                      -most_recent).days
            return {"status":"PASS",
                "source":"GOOGLE_SHEET_SFDC_EMAIL_QUOTATION_RAW",
                "source_state":"CURRENT_REPORT_DATE" if age_days<=1 else "STALE_REPORT_DATE",
                "quote_count":int(meta["quote_count"]),
                "process_rows":int(meta["line_count"]),
                "product_count":int(meta["quote_products"]),
                "unique_process_definitions":int(meta["process_definitions"]),
                "linked_sfdc_record_count":int(meta["linked_sfdc_ids"]),
                "unmapped_sfdc_record_count":int(meta["quote_count"])-int(meta["linked_sfdc_ids"]),
                "newest_quote_created_date":most_recent.isoformat(),
                "ingested_at_utc":meta["ingested_at_utc"],
                "currency":"USD_CONVERTED_ONLY","krw_rate_verified":False,
                "salesforce_write":False,"local_only":True}
        finally:cx.close()
    except (OSError,sqlite3.DatabaseError,ValueError,KeyError,ReportError):
        return {"status":"BLOCK","code":"SHEET_REPORT_UNAVAILABLE",
                "salesforce_write":False,"local_only":True}


def search(query="",limit=25):
    if not isinstance(query,str) or len(query)>80 or not isinstance(limit,int) or not 1<=limit<=30:
        raise ReportError("SHEET_SEARCH_INVALID")
    cx=_read()
    try:
        pattern="%"+query+"%"
        values=cx.execute("""SELECT h.business_quote_id,h.salesforce_record_id,
            h.account_name,h.contact_name,h.opportunity_name,h.created_date,h.active,
            COUNT(DISTINCT l.quotation_product_id),COUNT(l.row_number)
            FROM quote_headers h JOIN quote_process_lines l
                ON h.business_quote_id=l.business_quote_id
            JOIN process_dictionary p ON l.definition_hash=p.definition_hash
            WHERE h.business_quote_id LIKE ? OR h.account_name LIKE ?
               OR h.contact_name LIKE ? OR h.opportunity_name LIKE ?
               OR p.process_name LIKE ?
            GROUP BY h.business_quote_id
            ORDER BY h.created_date DESC,h.business_quote_id DESC LIMIT ?""",
            (pattern,pattern,pattern,pattern,pattern,limit)).fetchall()
        return {"status":"PASS","source_state":"REPORT_SNAPSHOT",
            "rows":[{"qid":r[0],"sfdc_record_id":r[1],
                "account_name":r[2],"contact_name":r[3],
                "opportunity_name":r[4],"created_date":r[5],
                "active":r[6]=="1","product_count":r[7],
                "process_lines":r[8]} for r in values],
            "currency":"USD_CONVERTED_ONLY","krw_rate_verified":False,
            "salesforce_write":False,"local_only":True}
    finally:cx.close()


def detail(identifier):
    if not isinstance(identifier,str) or len(identifier)>60 or not (
        QUOTE_ID.fullmatch(identifier) or SFDC_ID.fullmatch(identifier)):
        raise ReportError("SHEET_DETAIL_ID_INVALID")
    cx=_read()
    try:
        qid=identifier
        if identifier.startswith("a0P"):
            ids=cx.execute("""SELECT business_quote_id FROM quote_headers
                WHERE salesforce_record_id=?""",(identifier[:15],)).fetchall()
            if len(ids)!=1:raise ReportError("SHEET_SFDC_ID_UNMAPPED")
            qid=ids[0][0]
        q=cx.execute("""SELECT business_quote_id,salesforce_record_id,
            account_name,contact_name,opportunity_name,active,created_date
            FROM quote_headers WHERE business_quote_id=?""",(qid,)).fetchone()
        if not q:raise ReportError("SHEET_QUOTE_NOT_FOUND")
        lines=cx.execute("""SELECT l.quotation_product_id,p.process_id,p.process_name,
            p.data_unit,l.unit_price_usd,l.sales_price_usd,l.product_total_usd,
            l.sample_quantity,l.data_size
            FROM quote_process_lines l JOIN process_dictionary p
                ON l.definition_hash=p.definition_hash
            WHERE l.business_quote_id=? ORDER BY l.row_number LIMIT 121""",(qid,)).fetchall()
        if len(lines)>120:raise ReportError("SHEET_TOO_MANY_PROCESSES")
        return {"status":"PASS","source_state":"REPORT_SNAPSHOT",
            "qid":q[0],"sfdc_record_id":q[1],
            "account_name":q[2],"contact_name":q[3],
            "opportunity_name":q[4],"active":q[5]=="1",
            "created_date":q[6],
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
