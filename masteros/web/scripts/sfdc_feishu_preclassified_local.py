"""Private local read-through index of preclassified Feishu Quote references.

User-owned Feishu Base is canonical. This SQLite file is a temporary local
read-only search acceleration layer; it is refreshed explicitly from an
authenticated Chrome session and must match Quote row count and mail receipt
date before publishing. No Salesforce access, no CRM writes.
"""
from __future__ import annotations
import datetime as dt
import hashlib,json,os,re,sqlite3,time
from pathlib import Path
from collections import Counter
import sfdc_feishu_report_local as report

REFERENCE_TABLES={
 "reference":("tblkUTP09Sqy6vKk",{
    "Quote ID":"fldUfqmsnQ","Quote Record ID":"fldGZtSKpC",
    "Opportunity External ID":"fldTodYOXe","Opportunity Name":"fldLWHyOJH",
    "Account ID":"fldBILcIWE","Account Name":"fldSTYHq4h",
    "Contact ID":"fldoQK376K","Contact External ID":"fld46Bj6oK",
    "Contact Name":"fldJ8Io5Zm",
    "Contact Email":"fld7fQrGqX","Account Contact Status":"fldbWndNq2",
    "Products JSON":"fld29jBeYk","Product Count":"fldj7olHp6",
    "Reference Status":"fldgFxLZst","Source Exported KST":"fld6p7UlV1",
    "Source Received KST":"fldTJHqe7P","Reference SHA256":"flda8Qrnni",
 }),
 "class":("tbliXZAkyyjJjExe",{
    "Class Key":"fldU6BaB4b","Product Template Key":"fldZW3DQns",
    "Production Gb":"fldacktvZi","Gb Status":"fld0lVYrYU",
    "Source Exported KST":"fldzdKlLq5","Source Received KST":"fldpkv3gvX",
 })
}
DB=Path.home()/".sfdc_desktop"/"sfdc_feishu_quote_preclassified_PRIVATE.sqlite3"
SHA=re.compile(r"^[0-9a-f]{64}$")
ACCOUNT=re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
CONTACT=re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")

def _canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def _verified_refs(rows,classes,base):
    if not rows or not classes:raise report.FeishuSourceError("FEISHU_REFERENCE_INDEX_EMPTY")
    class_by_id={}
    for row in classes:
        key=row["Class Key"]
        if not SHA.fullmatch(key) or key in class_by_id or not SHA.fullmatch(row["Product Template Key"]):
            raise report.FeishuSourceError("FEISHU_PROJECT_CLASS_INVALID")
        class_by_id[key]=row
    refs={}
    class_used=set()
    count_products=0
    for row in rows:
        qid=row["Quote ID"]
        if not report.QID.fullmatch(qid) or qid in refs:
            raise report.FeishuSourceError("FEISHU_PREINDEX_QUOTE_ID_INVALID")
        checksum=row.get("Reference SHA256","")
        source={k:v for k,v in row.items() if k!="Reference SHA256"}
        if not SHA.fullmatch(checksum) or hashlib.sha256(
            _canonical(source).encode("utf-8")).hexdigest()!=checksum:
            raise report.FeishuSourceError("FEISHU_PREINDEX_CHECKSUM_MISMATCH")
        if row["Source Received KST"]!=base["source_mail_received_kst"]:
            raise report.FeishuSourceError("FEISHU_PREINDEX_SOURCE_TIME_MISMATCH")
        try:
            products=json.loads(row["Products JSON"])
        except (TypeError,ValueError):
            raise report.FeishuSourceError("FEISHU_PREINDEX_PRODUCTS_INVALID")
        if not isinstance(products,list) or len(products)<1 or len(products)>30 or len(products)!=int(row["Product Count"]):
            raise report.FeishuSourceError("FEISHU_PREINDEX_PRODUCT_COUNT_INVALID")
        for p in products:
            key=p.get("classKey") if isinstance(p,dict) else None
            if key not in class_by_id or not p.get("quoteProductId"):
                raise report.FeishuSourceError("FEISHU_PREINDEX_CLASS_REF_MISSING")
            if class_by_id[key]["Source Received KST"]!=base["source_mail_received_kst"]:
                raise report.FeishuSourceError("FEISHU_PREINDEX_CLASS_TIME_MISMATCH")
            class_used.add(key)
        count_products+=len(products)
        rid=row["Quote Record ID"]
        if rid and not report.SFDC_ID.fullmatch(rid):
            raise report.FeishuSourceError("FEISHU_PREINDEX_NATIVE_QUOTE_INVALID")
        account_id=row["Account ID"]
        if account_id and not ACCOUNT.fullmatch(account_id):
            raise report.FeishuSourceError("FEISHU_PREINDEX_ACCOUNT_INVALID")
        contact_id=row["Contact ID"]
        if contact_id and not CONTACT.fullmatch(contact_id):
            raise report.FeishuSourceError("FEISHU_PREINDEX_CONTACT_INVALID")
        refs[qid]=(row,products)
    if len(refs)!=base["quote_count"] or count_products!=base["product_count"]:
        raise report.FeishuSourceError("FEISHU_PREINDEX_SOURCE_COVERAGE_MISMATCH")
    if len(class_used)!=len(class_by_id):
        raise report.FeishuSourceError("FEISHU_PREINDEX_CLASS_ORPHAN")
    # Independent comparison: each preclassified QID/Quote Product must have
    # a corresponding line in the already validated local Feishu report cache.
    cx=report._connect()
    try:
        pairs={(q,p) for q,p in cx.execute(
            "SELECT DISTINCT qid,quote_product FROM quote_lines").fetchall()}
    finally:
        cx.close()
    indexed={(q,p["quoteProductId"]) for q,(_,products) in refs.items() for p in products}
    if indexed!=pairs:
        raise report.FeishuSourceError("FEISHU_PREINDEX_PRODUCT_IDENTITY_MISMATCH")
    return refs,class_by_id

def refresh():
    base=report.status()
    if base.get("status")!="PASS":raise report.FeishuSourceError("FEISHU_REPORT_NOT_SYNCED")
    for key,value in REFERENCE_TABLES.items():
        report.TABLES[key]=value
    from playwright.sync_api import sync_playwright
    t=time.monotonic()
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=12000)
        if not browser.contexts:raise report.FeishuSourceError("FEISHU_CHROME_SESSION_NOT_READY")
        context=browser.contexts[0]
        page=context.new_page()
        try:
            # The full Report Lines tab creates the authenticated GET pattern.
            _,_,seed=report._read_table(context,page,"lines")
            refs,r_rev,_=report._read_table(context,page,"reference",seed)
            classes,c_rev,_=report._read_table(context,page,"class",seed)
        finally:page.close()
    rows,class_by_id=_verified_refs(refs,classes,base)
    folder=DB.parent
    folder.mkdir(parents=True,exist_ok=True)
    if os.name!="nt":os.chmod(folder,0o700)
    stage=folder/"sfdc_preclassified_stage_PRIVATE.sqlite3"
    if stage.exists():stage.unlink()
    cx=sqlite3.connect(str(stage),timeout=15)
    try:
        with cx:
            cx.executescript("""CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
            CREATE TABLE project_classes(class_key TEXT PRIMARY KEY,
                template_key TEXT,gb TEXT,gb_status TEXT);
            CREATE TABLE quote_reference(qid TEXT PRIMARY KEY,
                quote_record_id TEXT,opportunity_external TEXT,opportunity_name TEXT,
                account_id TEXT,account_name TEXT,contact_id TEXT,contact_external_id TEXT,
                contact_name TEXT,contact_email TEXT,identity_status TEXT,
                products_json TEXT,reference_status TEXT,source_received TEXT,source_hash TEXT);
            CREATE INDEX ix_ref_account_name ON quote_reference(account_name);
            CREATE INDEX ix_ref_contact_name ON quote_reference(contact_name);
            CREATE INDEX ix_ref_contact_external ON quote_reference(contact_external_id);
            """)
            cx.executemany("INSERT INTO project_classes VALUES(?,?,?,?)",(
                (k,v["Product Template Key"],v["Production Gb"],v["Gb Status"])
                for k,v in class_by_id.items()))
            cx.executemany("INSERT INTO quote_reference VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                (qid,r["Quote Record ID"],r["Opportunity External ID"],r["Opportunity Name"],
                 r["Account ID"],r["Account Name"],r["Contact ID"],r.get("Contact External ID",""),
                 r["Contact Name"],r["Contact Email"],r["Account Contact Status"],
                 r["Products JSON"],r["Reference Status"],r["Source Received KST"],
                 r["Reference SHA256"])
                for qid,(r,_) in rows.items()))
            meta={
               "base_source_received":base["source_mail_received_kst"],
               "base_source_line_digest":base.get("source_line_digest",""),
               "base_quote_count":str(base["quote_count"]),
               "base_product_count":str(base["product_count"]),
               "quote_count":str(len(rows)),
               "class_count":str(len(class_by_id)),
               "reference_revision":str(r_rev),
               "class_revision":str(c_rev),
               "index_refreshed_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            }
            cx.executemany("INSERT INTO meta VALUES(?,?)",meta.items())
            if cx.execute("SELECT COUNT(*) FROM quote_reference").fetchone()[0]!=len(rows):
                raise report.FeishuSourceError("FEISHU_PREINDEX_SQLITE_READBACK_FAILED")
    finally:cx.close()
    if os.name!="nt":os.chmod(stage,0o600)
    os.replace(stage,DB)
    return {**status(),"loaded_in_seconds":round(time.monotonic()-t,1),
            "feishu_readback":"PASS","salesforce_write":False,
            "feishu_writes":0,"local_only":True}

def _open():
    return sqlite3.connect(str(DB),timeout=5)

def status():
    if not DB.is_file():
        return {"status":"BLOCK","code":"PRECLASSIFIED_INDEX_NOT_READY",
                "salesforce_write":False,"feishu_writes":0,"local_only":True}
    try:
        base=report.status()
        if base.get("status")!="PASS":
            raise report.FeishuSourceError("PREINDEX_BASE_NOT_READY")
        with _open() as cx:
            meta=dict(cx.execute("SELECT k,v FROM meta").fetchall())
            if (meta["base_source_received"]!=base["source_mail_received_kst"] or
                not meta.get("base_source_line_digest") or
                meta["base_source_line_digest"]!=base.get("source_line_digest") or
                int(meta["base_quote_count"])!=base["quote_count"] or
                int(meta["base_product_count"])!=base["product_count"]):
                raise report.FeishuSourceError("PREINDEX_STALE_RELATIVE_TO_SOURCE")
            return {"status":"PASS","source":"FEISHU_PRECLASSIFIED_QUOTE_REFERENCES",
                "quote_count":int(meta["quote_count"]),
                "project_classes":int(meta["class_count"]),
                "source_mail_received_kst":meta["base_source_received"],
                "indexed_at_utc":meta["index_refreshed_utc"],
                "index_freshness":"MATCHES_LOCAL_FEISHU_REPORT_SNAPSHOT",
                "line_digest_crosschecked":True,
                "salesforce_write":False,"feishu_writes":0,"local_only":True}
    except (OSError,sqlite3.DatabaseError,KeyError,ValueError,report.FeishuSourceError):
        return {"status":"BLOCK","code":"PRECLASSIFIED_INDEX_INTEGRITY_OR_FRESHNESS",
                "salesforce_write":False,"feishu_writes":0,"local_only":True}

def get_reference(qid):
    if status().get("status")!="PASS":return None
    with _open() as cx:
        row=cx.execute("""SELECT quote_record_id,opportunity_external,opportunity_name,
            account_id,account_name,contact_id,contact_external_id,
            contact_name,contact_email,identity_status,products_json,reference_status
            FROM quote_reference WHERE qid=?""",(qid,)).fetchone()
        if not row:return None
        return {
            "status":"PASS" if row[11]=="REFERENCE_ONLY" else "HOLD",
            "opportunityExternalId":row[1],"opportunityName":row[2],
            "accountId":row[3],"accountName":row[4],
            "contactId":row[5],"contactExternalId":row[6],
            "contactName":row[7],"contactEmail":row[8],
            "identityStatus":row[9],
            "products":json.loads(row[10]),
            "sourceQuoteRecordId":row[0],
            "preclassified":True
        }

def search_reference(term="",limit=20):
    if not isinstance(term,str) or len(term)>80 or not isinstance(limit,int) or not 1<=limit<=30:
        raise report.FeishuSourceError("PRECLASSIFIED_SEARCH_INVALID")
    if status().get("status")!="PASS":
        raise report.FeishuSourceError("PRECLASSIFIED_INDEX_NOT_READY")
    like="%"+term+"%"
    with _open() as cx:
        items=cx.execute("""SELECT qid,account_name,contact_name,opportunity_name,
            account_id,contact_id,contact_external_id,reference_status
            FROM quote_reference WHERE qid LIKE ? OR account_name LIKE ? OR
            contact_name LIKE ? OR opportunity_name LIKE ?
            ORDER BY qid DESC LIMIT ?""",(like,like,like,like,limit)).fetchall()
    return {"status":"PASS","source":"FEISHU_PRECLASSIFIED_QUOTE_REFERENCES",
            "rows":[{"qid":x[0],"account_name":x[1],"contact_name":x[2],
                "opportunity_name":x[3],"account_id":x[4],
                "contact_id":x[5],"contact_external_id":x[6],
                "identity_status":x[7]} for x in items],
            "salesforce_write":False,"feishu_writes":0,"local_only":True}


def identity_candidates(term,limit=15):
    """Search preclassified local reference identities, not live Salesforce.

    Each suggestion retains its source Quote, Account and Contact together.
    Same-name contacts at different institutions are never merged; IDs
    are reference evidence only, not confirmation of current CRM linkage.
    """
    if (not isinstance(term,str) or not 1<=len(term.strip())<=80 or
        not isinstance(limit,int) or not 1<=limit<=25):
        raise report.FeishuSourceError("IDENTITY_QUERY_INVALID")
    if status().get("status")!="PASS":
        raise report.FeishuSourceError("PRECLASSIFIED_INDEX_NOT_READY")
    needle=term.strip().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
    match="%"+needle+"%"
    with _open() as cx:
        records=cx.execute("""SELECT qid,account_id,account_name,
              contact_id,contact_external_id,contact_name,contact_email,
              identity_status
              FROM quote_reference
              WHERE (contact_name LIKE ? ESCAPE '\\'
                 OR account_name LIKE ? ESCAPE '\\'
                 OR contact_email LIKE ? ESCAPE '\\'
                 OR contact_external_id LIKE ? ESCAPE '\\')
              AND account_name!='' AND contact_name!=''
              ORDER BY qid DESC LIMIT 250""",
              (match,match,match,match)).fetchall()
    distinct=set()
    candidates=[]
    for r in records:
        # Retain institution in key even for homonymous Contacts without 003 IDs.
        identity=(r[1],r[2],r[3],r[4],r[5],r[6])
        if identity in distinct:continue
        distinct.add(identity)
        candidates.append({
            "source_qid":r[0],"account_id":r[1],"account_name":r[2],
            "contact_id":r[3],"contact_external_id":r[4],
            "contact_name":r[5],"contact_email":r[6],
            "identity_status":r[7],
            "crm_contact_verified":bool(CONTACT.fullmatch(r[3] or "")),
            "crm_account_verified":bool(ACCOUNT.fullmatch(r[1] or ""))
        })
        if len(candidates)>=limit:break
    return {"status":"PASS","source":"FEISHU_PRECLASSIFIED_QUOTE_REFERENCES",
        "rows":candidates,"source_only":True,"salesforce_write":False,
        "feishu_writes":0,"local_only":True}
