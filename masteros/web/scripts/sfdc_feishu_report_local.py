"""Read a logged-in user's Feishu Quote Report Base directly, without CRM access.

Source: existing Feishu Bitable via authenticated Chrome CDP session.
The user's browser provides session authentication. No app secrets or customer
data are exposed in stdout/GitHub. Only GET requests; no Feishu writes.
A private SQLite index accelerates local search. It is a *cache*, not truth.
"""
from __future__ import annotations

import base64
import hashlib
import datetime as dt
from decimal import Decimal, InvalidOperation
import gzip
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.parse

APP="IpMkbUD0vaFqtYs93a3csXtdn1b"
HOST="ocnz4cb25scn.feishu.cn"
TABLES={
    "lines":("tblHme64Ccdj4Fwv",{
        "Line Key":"fldBOWub4z",
        "Quote ID":"fldU0vF634",
        "Quote Record ID":"fldK8FELbi",
        "Quote Product ID":"fldVjC5s20",
        "Product Template Key":"fldvRVcfSb",
        "Process Key":"fldWdmQTXn",
        "Unit Price USD":"fldAHur8Dk",
        "Sales Price USD":"fldQcSe1ex",
        "Process Total USD":"fldJ8Km1l7",
        "Sample Qty":"fldkvrN43R",
        "Data Size":"flds5D04mk",
        "Active":"fldfqnLBjF",
        "Quote Created":"fld9lGYlIi",
        "Source Exported KST":"fld7IKVveb",
        "Source Received KST":"fld1GGhINh",
        "Source Row Hash":"fldIftYE0C",
        "Source Status":"fldUbRXH77",
    }),
    "process":("tblD2XMNWeAcvGWe",{
        "Process Key":"fldTxiN0fO",
        "Process ID":"fldSLUQsPH",
        "Process Name":"fld5NRMd13",
        "Data Unit":"fldjAnKMbl",
        "Source Exported KST":"fldYUj5Kyx",
        "Source Received KST":"fldom78Kst",
    }),
    "product":("tbl2tGZyBlEbyruO",{
        "Product Template Key":"fldKJ2bmNq",
        "Process Keys":"fldVoh4j37",
        "Process Count":"fld9uFvsFR",
        "Source Exported KST":"fldsH5z43G",
        "Source Received KST":"fldENK6a1H",
    }),
}
DB_DIR=Path.home()/".sfdc_desktop"
DB_PATH=DB_DIR/"sfdc_feishu_quote_report_PRIVATE.sqlite3"
MAX_PAGE=3000
MAX_REPORT_ROWS=5000
MAX_SOURCE_BYTES=20*1024*1024
SOURCE="FEISHU_BASE_QUOTE_REPORT_LINES"
QID=re.compile(r"^QID-[0-9-]{8,50}$")
SHA=re.compile(r"^[a-f0-9]{64}$")
SFDC_ID=re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")


class FeishuSourceError(ValueError):
    pass


def _text(cell):
    if not isinstance(cell,dict):
        return ""
    v=cell.get("value")
    if v is None:return ""
    if isinstance(v,list):
        return "".join(str(x.get("text","")) for x in v if isinstance(x,dict)).strip()
    if isinstance(v,(str,int,float)) and not isinstance(v,bool):
        return str(v).strip()
    raise FeishuSourceError("FEISHU_CELL_UNEXPECTED_TYPE")


def _url_for(table):
    return "https://"+HOST+"/base/"+APP+"?table="+TABLES[table][0]


def _decode(response,table):
    if response.status!=200:raise FeishuSourceError("FEISHU_HTTP_UNAVAILABLE")
    obj=response.json()
    if obj.get("code")!=0 or not isinstance(obj.get("data"),dict):
        raise FeishuSourceError("FEISHU_RECORD_API_REJECTED")
    container=obj["data"]
    raw=container.get("records")
    if container.get("encoding")!=0 or not isinstance(raw,str) or len(raw)>MAX_SOURCE_BYTES:
        raise FeishuSourceError("FEISHU_RECORD_ENCODING_UNSUPPORTED")
    try:
        decompressed=gzip.decompress(base64.b64decode(raw,validate=True))
        if len(decompressed)>MAX_SOURCE_BYTES:
            raise FeishuSourceError("FEISHU_PAGE_TOO_LARGE")
        value=json.loads(decompressed)
    except (ValueError,OSError,gzip.BadGzipFile) as exc:
        raise FeishuSourceError("FEISHU_RECORD_DECODE_FAILED") from exc
    if not isinstance(value,dict) or value.get("tableID")!=TABLES[table][0]:
        raise FeishuSourceError("FEISHU_WRONG_TABLE")
    records=value.get("recordMap")
    total=value.get("tableRecordNum")
    if not isinstance(records,dict) or not isinstance(total,int) or not 0<total<=MAX_REPORT_ROWS:
        raise FeishuSourceError("FEISHU_RECORD_COUNT_INVALID")
    return value


def _read_table(context,page,kind,source_request=None):
    """Use the authenticated Feishu UI request pattern; read exact table only.

    Small dictionary tables do not issue automatic /records requests when
    opened. The same authenticated GET with no viewId reads them safely.
    """
    table_id,ids=TABLES[kind]
    captured=[]
    def handler(req):
        path=urllib.parse.urlsplit(req.url).path
        if (req.method=="GET" and
            path==f"/space/api/v1/bitable/{APP}/records"):
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(req.url).query)
            if query.get("tableId")==[table_id]:
                captured.append(req.url)
    if source_request is None:
        page.on("request",handler)
        try:
            page.goto(_url_for(kind),wait_until="domcontentloaded",timeout=35000)
            until=time.monotonic()+19
            while not captured and time.monotonic()<until:
                page.wait_for_timeout(700)
        finally:
            page.remove_listener("request",handler)
        if not captured:
            raise FeishuSourceError("FEISHU_AUTHENTICATED_RECORD_REQUEST_MISSING")
        seed=captured[-1]
    else:
        seed=source_request

    original=urllib.parse.urlsplit(seed)
    if (original.scheme!="https" or original.hostname!=HOST or
        original.path!=f"/space/api/v1/bitable/{APP}/records"):
        raise FeishuSourceError("FEISHU_REQUEST_HOST_INVALID")
    params={k:v[0] for k,v in urllib.parse.parse_qs(original.query).items()}
    if source_request is not None:
        params["tableId"]=table_id
        params["tableID"]=table_id
        # A view from the Lines table is not valid on other tables.
        # This Feishu API accepts exact table reads with no view ID.
        for key in ("viewId","viewID","viewLazyLoad","tableRev","depRev"):
            params.pop(key,None)

    rows={}
    total_expected=None
    revision=None
    for offset in range(0,MAX_REPORT_ROWS,MAX_PAGE):
        params.update({"offset":str(offset),"limit":str(MAX_PAGE)})
        url=urllib.parse.urlunsplit((original.scheme,original.netloc,original.path,
            urllib.parse.urlencode(params),""))
        res=context.request.get(url,timeout=35000)
        data=_decode(res,kind)
        total=data["tableRecordNum"]
        if total_expected is None:
            total_expected=total
            revision=data.get("tableRev")
        elif total!=total_expected or data.get("tableRev")!=revision:
            raise FeishuSourceError("FEISHU_SOURCE_MUTATED_DURING_READ")
        entries=data["recordMap"]
        if len(entries)>MAX_PAGE or len(rows)+len(entries)>MAX_REPORT_ROWS:
            raise FeishuSourceError("FEISHU_PAGE_COUNT_OUT_OF_RANGE")
        for recid,cells in entries.items():
            if recid in rows or not isinstance(cells,dict):
                raise FeishuSourceError("FEISHU_RECORD_DUPLICATED")
            parsed={key:_text(cells.get(fid)) for key,fid in ids.items()}
            rows[recid]=parsed
        if len(rows)==total:
            break
    if len(rows)!=total_expected:
        raise FeishuSourceError("FEISHU_RECORD_PAGINATION_INCOMPLETE")
    return list(rows.values()),revision,seed


def _read_all_from_browser():
    from playwright.sync_api import sync_playwright
    started=time.monotonic()
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=12000)
        if not browser.contexts:
            raise FeishuSourceError("CHROME_FEISHU_LOGIN_CONTEXT_UNAVAILABLE")
        context=browser.contexts[0]
        page=context.new_page()
        try:
            lines,l_rev,seed=_read_table(context,page,"lines")
            process,p_rev,_=_read_table(context,page,"process",seed)
            product,t_rev,_=_read_table(context,page,"product",seed)
        finally:
            page.close()
    return lines,process,product,{"lines":l_rev,"process":p_rev,"product":t_rev},round(time.monotonic()-started,1)


def _decimal(v):
    if v in ("","-","null","None"):return ""
    try:
        x=Decimal(v.replace(",",""))
        if not x.is_finite() or abs(x)>Decimal("999999999999"):
            raise InvalidOperation
        return format(x,"f")
    except (InvalidOperation,AttributeError):
        raise FeishuSourceError("FEISHU_AMOUNT_INVALID")


def _validate(lines,process,product):
    if not lines or not process or not product:
        raise FeishuSourceError("FEISHU_EMPTY_REFERENCE_TABLE")
    procs={}
    for p in process:
        key=p["Process Key"]
        if not SHA.fullmatch(key) or not p["Process ID"] or not p["Process Name"] or key in procs:
            raise FeishuSourceError("FEISHU_PROCESS_REFERENCE_INVALID")
        procs[key]=p
    templates={}
    for p in product:
        key=p["Product Template Key"]
        if not SHA.fullmatch(key) or key in templates:
            raise FeishuSourceError("FEISHU_PRODUCT_REFERENCE_INVALID")
        try:
            keys=json.loads(p["Process Keys"])
        except (ValueError,TypeError):
            raise FeishuSourceError("FEISHU_PRODUCT_TEMPLATE_INVALID")
        if (not isinstance(keys,list) or not keys or
            not all(isinstance(x,str) and x in procs for x in keys) or
            p["Process Count"]!=str(len(keys))):
            raise FeishuSourceError("FEISHU_PRODUCT_TEMPLATE_INCOMPLETE")
        templates[key]=p
    unique=set()
    quote=set()
    quote_product=set()
    export_times=set()
    received_times=set()
    for row in lines:
        key=row["Line Key"]
        if not SHA.fullmatch(key) or key in unique:
            raise FeishuSourceError("FEISHU_LINE_KEY_INVALID")
        unique.add(key)
        if not QID.fullmatch(row["Quote ID"]) or not row["Quote Product ID"]:
            raise FeishuSourceError("FEISHU_QUOTE_PRODUCT_INVALID")
        rid=row["Quote Record ID"]
        if rid and not SFDC_ID.fullmatch(rid):
            raise FeishuSourceError("FEISHU_NATIVE_QUOTE_ID_INVALID")
        if row["Process Key"] not in procs or row["Product Template Key"] not in templates:
            raise FeishuSourceError("FEISHU_REFERENCE_MISSING")
        for f in ("Unit Price USD","Sales Price USD","Process Total USD","Sample Qty","Data Size"):
            row[f]=_decimal(row[f])
        export_times.add(row["Source Exported KST"])
        received_times.add(row["Source Received KST"])
        quote.add(row["Quote ID"])
        quote_product.add((row["Quote ID"],row["Quote Product ID"]))
    if len(export_times)!=1:
        raise FeishuSourceError("FEISHU_SOURCE_EXPORT_TIMES_CONFLICT")
    if len(received_times)!=1 or not next(iter(received_times)):
        raise FeishuSourceError("FEISHU_MAIL_RECEIPT_SOURCE_MISSING")
    try:
        received=dt.datetime.strptime(next(iter(received_times)),"%Y-%m-%d %H:%M:%S KST").replace(
            tzinfo=dt.timezone(dt.timedelta(hours=9)))
    except ValueError:
        raise FeishuSourceError("FEISHU_MAIL_RECEIPT_DATE_INVALID")
    if received>dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10):
        raise FeishuSourceError("FEISHU_MAIL_RECEIPT_DATE_IN_FUTURE")
    # Quote creation date can establish data coverage but never proves the
    # subscribed process-report email receipt timestamp.
    created=[]
    for row in lines:
        try:
            created.append(dt.datetime.strptime(row["Quote Created"],"%m/%d/%Y").date())
        except (ValueError,KeyError):
            continue
    return {"quote_count":len(quote),"product_count":len(quote_product),
            "process_rows":len(lines),"unique_process_definitions":len(procs),
            "product_templates":len(templates),
            "latest_quote_created":max(created).isoformat() if created else "",
            "source_report_exported_kst":next(iter(export_times)),
            "source_mail_received_kst":next(iter(received_times))}


def _connect():
    c=sqlite3.connect(str(DB_PATH),timeout=6)
    c.execute("PRAGMA busy_timeout=6000")
    return c


def refresh():
    raw_lines,process,product,revisions,elapsed=_read_all_from_browser()
    superseded=[r for r in raw_lines if r.get("Source Status")=="SUPERSEDED_NOT_IN_CURRENT_REPORT"]
    if len(superseded)>100 or len(superseded)>max(10,len(raw_lines)//50):
        raise FeishuSourceError("FEISHU_HISTORICAL_DRIFT_TOO_LARGE")
    lines=[r for r in raw_lines if r.get("Source Status")!="SUPERSEDED_NOT_IN_CURRENT_REPORT"]
    summary=_validate(lines,process,product)
    summary["physical_feishu_rows"]=len(raw_lines)
    summary["historical_retained_rows"]=len(superseded)
    # Fingerprint only once per Feishu refresh, never in hot search/detail paths.
    # A mail re-import may change values without changing row count or date.
    ordered=sorted((r["Line Key"],r["Source Row Hash"]) for r in lines)
    summary["source_line_digest"]=hashlib.sha256(json.dumps(
        ordered,ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
    DB_DIR.mkdir(parents=True,exist_ok=True)
    if os.name!="nt":os.chmod(DB_DIR,0o700)
    staged=DB_DIR/"feishu_quote_report_stage_PRIVATE.sqlite3"
    if staged.exists():staged.unlink()
    cx=sqlite3.connect(str(staged),timeout=10)
    checked=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        with cx:
            cx.executescript("""CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
                CREATE TABLE process_dict(process_key TEXT PRIMARY KEY,
                    process_id TEXT,process_name TEXT,data_unit TEXT);
                CREATE TABLE quote_lines(
                    line_key TEXT PRIMARY KEY,qid TEXT NOT NULL,quote_record_id TEXT,
                    quote_product TEXT NOT NULL,product_template TEXT NOT NULL,
                    process_key TEXT NOT NULL,unit_usd TEXT,sales_usd TEXT,total_usd TEXT,
                    sample_qty TEXT,data_size TEXT,active TEXT,created TEXT,
                    exported_kst TEXT,received_kst TEXT,row_hash TEXT,source_status TEXT,
                    FOREIGN KEY(process_key) REFERENCES process_dict(process_key));
                CREATE INDEX ix_feishu_qid ON quote_lines(qid);
                CREATE INDEX ix_feishu_product ON quote_lines(quote_product);
                CREATE INDEX ix_feishu_process ON quote_lines(process_key);
            """)
            cx.executemany("INSERT INTO process_dict VALUES(?,?,?,?)",(
                (r["Process Key"],r["Process ID"],r["Process Name"],r["Data Unit"])
                for r in process))
            cx.executemany("INSERT INTO quote_lines VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                (r["Line Key"],r["Quote ID"],r["Quote Record ID"],
                 r["Quote Product ID"],r["Product Template Key"],
                 r["Process Key"],r["Unit Price USD"],r["Sales Price USD"],
                 r["Process Total USD"],r["Sample Qty"],r["Data Size"],
                 r["Active"],r["Quote Created"],r["Source Exported KST"],
                 r["Source Received KST"],r["Source Row Hash"],r["Source Status"]) for r in lines))
            meta={**summary,
                  "source":SOURCE,
                  "feishu_synced_at_utc":checked,
                  "feishu_table_id":TABLES["lines"][0],
                  "feishu_revision":str(revisions["lines"]),
                  "currency":"USD_CONVERTED_ONLY",
                  "krw_rate_verified":"false"}
            cx.executemany("INSERT INTO meta VALUES(?,?)",((k,str(v)) for k,v in meta.items()))
            actual=cx.execute("SELECT count(*) FROM quote_lines").fetchone()[0]
            if actual!=summary["process_rows"]:
                raise FeishuSourceError("FEISHU_SINK_READBACK_MISMATCH")
    finally:
        cx.close()
    if os.name!="nt":os.chmod(staged,0o600)
    os.replace(staged,DB_PATH)
    return {**status(),"load_seconds":elapsed,"feishu_sink_readback":"PASS",
            "feishu_writes":0,"crm_writes":0}


def status():
    if not DB_PATH.is_file():
        return {"status":"BLOCK","code":"FEISHU_REPORT_NOT_SYNCED",
                "salesforce_write":False,"feishu_writes":0,"local_only":True}
    try:
        cx=_connect()
        try:
            meta=dict(cx.execute("SELECT k,v FROM meta").fetchall())
            source=meta["source_report_exported_kst"]
            receipt=meta.get("source_mail_received_kst","")
            try:
                when=dt.datetime.strptime(receipt,"%Y-%m-%d %H:%M:%S KST").replace(
                    tzinfo=dt.timezone(dt.timedelta(hours=9)))
                elapsed=(dt.datetime.now(dt.timezone.utc)-when).total_seconds()
                source_state=("STALE_MAIL_SOURCE" if elapsed>48*3600
                              else "MAIL_RECEIPT_VERIFIED_EXPORT_UNVERIFIED")
            except ValueError:
                source_state="PROCESS_REPORT_RECEIPT_UNVERIFIED"
            return {"status":"PASS","source":SOURCE,
                "source_state":source_state,
                "feishu_snapshot_state":"CACHED_FROM_AUTHENTICATED_FEISHU",
                "quote_count":int(meta["quote_count"]),
                "product_count":int(meta["product_count"]),
                "process_rows":int(meta["process_rows"]),
                "unique_process_definitions":int(meta["unique_process_definitions"]),
                "product_template_count":int(meta["product_templates"]),
                "physical_feishu_rows":int(meta.get("physical_feishu_rows",meta["process_rows"])),
                "historical_retained_rows":int(meta.get("historical_retained_rows","0")),
                "linked_sfdc_record_count":cx.execute(
                    "SELECT count(distinct qid) FROM quote_lines WHERE quote_record_id!=''").fetchone()[0],
                "unmapped_sfdc_record_count":cx.execute(
                    "SELECT count(distinct qid) FROM quote_lines WHERE quote_record_id=''").fetchone()[0],
                "source_report_exported_kst":source,
                "source_mail_received_kst":receipt,
                "source_mail_timestamp_verified":bool(receipt),
                "process_export_time_verified":False,
                "latest_quote_created":meta.get("latest_quote_created",""),
                "ingested_at_utc":meta["feishu_synced_at_utc"],
                "feishu_revision":meta["feishu_revision"],
                "source_line_digest":meta.get("source_line_digest",""),
                "currency":"USD_CONVERTED_ONLY",
                "krw_rate_verified":False,"salesforce_write":False,
                "feishu_writes":0,"local_only":True}
        finally:cx.close()
    except (OSError,sqlite3.DatabaseError,TypeError,ValueError,KeyError):
        return {"status":"BLOCK","code":"FEISHU_REPORT_CACHE_CORRUPT",
                "salesforce_write":False,"feishu_writes":0,"local_only":True}


def search(query="",limit=25):
    if not isinstance(query,str) or len(query)>80 or not isinstance(limit,int) or not 1<=limit<=30:
        raise FeishuSourceError("FEISHU_SEARCH_INVALID")
    if status().get("status")!="PASS":
        raise FeishuSourceError("FEISHU_REPORT_NOT_SYNCED")
    try:
        import sfdc_feishu_preclassified_local as pre
        if pre.status().get("status")=="PASS":
            matching=pre.search_reference(query,limit)
            with _connect() as db:
                items=[]
                for row in matching["rows"]:
                    data=db.execute("""SELECT COUNT(DISTINCT quote_product),COUNT(*),
                        MAX(created),MAX(source_status),MAX(quote_record_id)
                        FROM quote_lines WHERE qid=?""",(row["qid"],)).fetchone()
                    if data and data[1]:
                        items.append({"qid":row["qid"],"sfdc_record_id":data[4],
                            "product_count":data[0],"process_lines":data[1],
                            "created_date":data[2],"source_status":data[3],
                            "account_name":row["account_name"],
                            "contact_name":row["contact_name"],
                            "opportunity_name":row["opportunity_name"]})
            return {"status":"PASS","source":"FEISHU_PRECLASSIFIED_QUOTE_REFERENCES",
                "source_state":status()["source_state"],"rows":items,
                "currency":"USD_CONVERTED_ONLY","krw_rate_verified":False,
                "salesforce_write":False,"feishu_writes":0,"local_only":True}
    except (ImportError,FeishuSourceError,OSError,sqlite3.DatabaseError,ValueError):
        pass
    cx=_connect()
    try:
        pat="%"+query+"%"
        rows=cx.execute("""SELECT l.qid,max(l.quote_record_id),
            count(distinct l.quote_product),count(*),
            max(l.created),max(l.source_status)
            FROM quote_lines l JOIN process_dict p ON p.process_key=l.process_key
            WHERE l.qid LIKE ? OR l.quote_product LIKE ? OR p.process_name LIKE ?
            GROUP BY l.qid ORDER BY max(l.created) DESC,l.qid DESC LIMIT ?""",
            (pat,pat,pat,limit)).fetchall()
        return {"status":"PASS","source":SOURCE,"source_state":status()["source_state"],
                "rows":[{"qid":r[0],"sfdc_record_id":r[1],
                         "product_count":r[2],"process_lines":r[3],
                         "created_date":r[4],"source_status":r[5],
                         "account_name":"","contact_name":""} for r in rows],
                "currency":"USD_CONVERTED_ONLY","krw_rate_verified":False,
                "salesforce_write":False,"feishu_writes":0,"local_only":True}
    finally:cx.close()


def detail(identifier):
    if not isinstance(identifier,str) or not (QID.fullmatch(identifier) or SFDC_ID.fullmatch(identifier)):
        raise FeishuSourceError("FEISHU_QUOTE_ID_INVALID")
    if status().get("status")!="PASS":
        raise FeishuSourceError("FEISHU_REPORT_NOT_SYNCED")
    cx=_connect()
    try:
        if identifier.startswith("a0P"):
            qids=cx.execute("SELECT distinct qid FROM quote_lines WHERE quote_record_id=?",
                            (identifier,)).fetchall()
            if len(qids)!=1:raise FeishuSourceError("FEISHU_QUOTE_RECORD_ID_UNMAPPED")
            identifier=qids[0][0]
        rows=cx.execute("""SELECT l.quote_product,p.process_id,p.process_name,p.data_unit,
            l.unit_usd,l.sales_usd,l.total_usd,l.sample_qty,l.data_size,
            l.quote_record_id,l.source_status,l.exported_kst,l.received_kst
            FROM quote_lines l JOIN process_dict p ON p.process_key=l.process_key
            WHERE l.qid=? ORDER BY l.created,l.line_key LIMIT 121""",
            (identifier,)).fetchall()
        if not rows:raise FeishuSourceError("FEISHU_QUOTE_NOT_FOUND")
        if len(rows)>120:raise FeishuSourceError("FEISHU_QUOTE_TOO_MANY_LINES")
        rec_ids={r[9] for r in rows}
        if len(rec_ids)!=1:raise FeishuSourceError("FEISHU_QUOTE_RECORD_ID_CONFLICT")
        try:
            import sfdc_feishu_preclassified_local as pre
            reference=pre.get_reference(identifier)
        except (ImportError,OSError,sqlite3.DatabaseError,FeishuSourceError):
            reference=None
        if reference is not None and reference.get("sourceQuoteRecordId")!=rows[0][9]:
            raise FeishuSourceError("FEISHU_PREINDEX_QUOTE_IDENTITY_CONFLICT")
        return {"status":"PASS","source":SOURCE,"source_state":status()["source_state"],
            "reference":reference,
            "qid":identifier,"sfdc_record_id":rows[0][9],
            "product_count":len({r[0] for r in rows}),
            "source_report_exported_kst":rows[0][11],
            "source_mail_received_kst":rows[0][12],
            "process_lines":[{"quotation_product_id":r[0],"process_id":r[1],
                "process_name":r[2],"data_unit":r[3],
                "unit_price_usd":r[4],"sales_price_usd_converted":r[5],
                "product_total_usd_converted":r[6],
                "sample_quantity":r[7],"data_size":r[8]}
                for r in rows],
            "currency":"USD_CONVERTED_ONLY","krw_rate_verified":False,
            "salesforce_write":False,"feishu_writes":0,"local_only":True}
    finally:cx.close()


def run(request):
    if not isinstance(request,dict):
        raise FeishuSourceError("FEISHU_INPUT_INVALID")
    mode=request.get("mode")
    if mode=="STATUS":return status()
    if mode=="REFRESH":
        result=refresh()
        import sfdc_feishu_preclassified_local as pre
        proof=pre.refresh()
        return {**result,"preclassified":proof,
                "preclassified_ready":proof.get("status")=="PASS"}
    if mode=="REFRESH_REFERENCES":
        import sfdc_feishu_preclassified_local as pre
        return pre.refresh()
    if mode=="REFERENCE_STATUS":
        import sfdc_feishu_preclassified_local as pre
        return pre.status()
    if mode=="IDENTITY_SEARCH":
        import sfdc_feishu_preclassified_local as pre
        return pre.identity_candidates(request.get("query",""),request.get("limit",15))
    if mode=="OPPORTUNITY_SEARCH":
        import sfdc_feishu_preclassified_local as pre
        return pre.search_opportunities(request.get("query",""),request.get("limit",25))
    if mode=="OPPORTUNITY_QUOTES":
        import sfdc_feishu_preclassified_local as pre
        return pre.opportunity_quotes(request.get("opportunityExternal",""))
    if mode=="SEARCH":return search(request.get("query",""),request.get("limit",25))
    if mode=="DETAIL":return detail(request.get("id"))
    raise FeishuSourceError("FEISHU_READ_ONLY_MODE_REQUIRED")


if __name__=="__main__":
    try:
        data=sys.stdin.buffer.read(1024)
        if len(data)>1000:raise FeishuSourceError("INPUT_TOO_LARGE")
        request=json.loads(data.decode("utf-8"))
        result=run(request)
    except (FeishuSourceError,ValueError,TypeError,UnicodeError):
        result={"status":"BLOCK","code":"FEISHU_SOURCE_OR_INPUT_INVALID",
            "salesforce_write":False,"feishu_writes":0,"local_only":True}
    except Exception:
        result={"status":"BLOCK","code":"FEISHU_BROWSER_SOURCE_UNAVAILABLE",
            "salesforce_write":False,"feishu_writes":0,"local_only":True}
    print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
