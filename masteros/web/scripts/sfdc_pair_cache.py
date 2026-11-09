"""Private operator-PC cache for Salesforce read-only quote picker evidence.

Only valid authenticated UI reads are persisted. This is NOT Salesforce source
of truth, never authorizes CRM saves, and cannot replace independent new-Quote
readback. TTLs are intentionally short; expired rows are not used as prices.

No network, credentials, emails, debug dumps or customer IDs in stdout/logs.
The SQLite database remains under the logged-in user's home directory.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from sfdc_product_line_registry import compact, expand, refs, compact_json, TemplateIntegrityError

CACHE_DIR=Path.home()/".sfdc_desktop"
CACHE_FILE=CACHE_DIR/"sf_oppo_quote_prices_PRIVATE.sqlite3"
VERSION=1
TTL_SECONDS={"list":900,"bundle":1200,"detail":900}
MAX_RECORD_BYTES=240000
RECORD_ID=re.compile(r"^(?:006|a0P)[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")


def _db():
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    if os.name!="nt":
        os.chmod(CACHE_DIR,0o700)
    cx=sqlite3.connect(str(CACHE_FILE),timeout=6)
    if os.name!="nt":
        os.chmod(CACHE_FILE,0o600)
    cx.execute("PRAGMA busy_timeout=6000")
    cx.execute("""CREATE TABLE IF NOT EXISTS entries(
        cache_key TEXT PRIMARY KEY,kind TEXT NOT NULL,
        observed_utc INTEGER NOT NULL,expires_utc INTEGER NOT NULL,
        schema_version INTEGER NOT NULL,content_sha256 TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )""")
    cx.execute("""CREATE TABLE IF NOT EXISTS product_line_templates(
        template_sha256 TEXT PRIMARY KEY,
        content_json TEXT NOT NULL,
        last_seen_utc INTEGER NOT NULL
    )""")
    return cx


@contextmanager
def _connect():
    """sqlite3.Connection context alone does not close on Windows."""
    cx=_db()
    try:
        with cx:
            yield cx
    finally:
        cx.close()


def key_for(request):
    """Only whitelist exact read-only operations. Never cache searches."""
    if not isinstance(request,dict):
        return None
    if request.get("resource")=="opportunity" and request.get("mode")=="list" and not request.get("query"):
        return "opportunity:list", "list"
    if request.get("resource")=="opportunity" and request.get("mode")=="bundle":
        rid=request.get("recordId")
        if isinstance(rid,str) and rid.startswith("006") and RECORD_ID.fullmatch(rid):
            return "opportunity:bundle:"+rid,"bundle"
    if request.get("resource") in ("opportunity","quote") and request.get("mode")=="detail":
        rid=request.get("recordId")
        prefix="006" if request["resource"]=="opportunity" else "a0P"
        if isinstance(rid,str) and rid.startswith(prefix) and RECORD_ID.fullmatch(rid):
            return request["resource"]+":detail:"+rid,"detail"
    return None


def _valid(request,output):
    identity=key_for(request)
    if identity is None or not isinstance(output,dict) or output.get("status")!="PASS" or output.get("read_only") is not True:
        return False
    kind=identity[1]
    if kind=="list":
        records=output.get("records")
        return (output.get("resource")=="opportunity" and
                output.get("scope")=="SALESFORCE_CURRENT_LIST_VIEW" and
                isinstance(records,list) and len(records)<=30 and
                all(isinstance(r,dict) and isinstance(r.get("id"),str) and
                    r["id"].startswith("006") and RECORD_ID.fullmatch(r["id"]) for r in records))
    if kind=="detail":
        return (output.get("id")==request["recordId"] and output.get("source")=="LIVE_SALESFORCE"
                and output.get("resource")==request["resource"])
    opp=output.get("opportunity")
    quotes=output.get("linkedQuotes")
    return (output.get("selectionStatus")=="EXACT_ONE" and output.get("quoteCount")==1 and
            isinstance(opp,dict) and opp.get("id")==request["recordId"] and
            opp.get("source")=="LIVE_SALESFORCE" and opp.get("read_only") is True and
            isinstance(quotes,list) and len(quotes)==1 and isinstance(quotes[0],dict) and
            quotes[0].get("source")=="LIVE_SALESFORCE" and quotes[0].get("read_only") is True and
            quotes[0].get("opportunityId")==opp["id"] and
            isinstance(quotes[0].get("id"),str) and quotes[0]["id"].startswith("a0P") and
            bool(RECORD_ID.fullmatch(quotes[0]["id"])))


def _iso(seconds):
    return dt.datetime.fromtimestamp(seconds,dt.timezone.utc).isoformat(timespec="seconds")


def _prune_unused_templates(cx):
    """Remove templates with no references in the retained cache."""
    used=set()
    for (raw,) in cx.execute("SELECT payload_json FROM entries").fetchall():
        try:
            used.update(refs(json.loads(raw)))
        except (TypeError,ValueError,AttributeError):
            return  # Do not delete metadata when a retained row is unreadable.
    for (identifier,) in cx.execute("SELECT template_sha256 FROM product_line_templates").fetchall():
        if identifier not in used:
            cx.execute("DELETE FROM product_line_templates WHERE template_sha256=?",(identifier,))


def save(request,output,now=None):
    if not _valid(request,output):
        return False
    key,kind=key_for(request)
    # Only shared structural metadata is normalized; per-customer prices,
    # pack quantity, discounts and Quote IDs remain in the individual snapshot.
    payload={k:v for k,v in output.items() if k!="cache"}
    try:
        payload,templates=compact(payload)
    except (TemplateIntegrityError,TypeError,ValueError):
        return False
    raw=compact_json(payload)
    if len(raw.encode("utf-8"))>MAX_RECORD_BYTES:
        return False
    checked=int(time.time() if now is None else now)
    sha=hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with _connect() as cx:
        for identifier,template in templates.items():
            cx.execute("""INSERT INTO product_line_templates(
                template_sha256,content_json,last_seen_utc)
                VALUES(?,?,?)
                ON CONFLICT(template_sha256) DO UPDATE SET
                last_seen_utc=excluded.last_seen_utc""",
                (identifier,compact_json(template),checked))
        cx.execute("""INSERT INTO entries(cache_key,kind,observed_utc,expires_utc,schema_version,content_sha256,payload_json)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(cache_key) DO UPDATE SET kind=excluded.kind,
            observed_utc=excluded.observed_utc,expires_utc=excluded.expires_utc,
            schema_version=excluded.schema_version,content_sha256=excluded.content_sha256,
            payload_json=excluded.payload_json""",
            (key,kind,checked,checked+TTL_SECONDS[kind],VERSION,sha,raw))
        cx.execute("DELETE FROM entries WHERE expires_utc<?",(checked-86400,))
        _prune_unused_templates(cx)
    return True


def lookup(request,now=None):
    identity=key_for(request)
    if identity is None:
        return None
    checked=int(time.time() if now is None else now)
    try:
        with _connect() as cx:
            row=cx.execute("""SELECT observed_utc,expires_utc,schema_version,content_sha256,payload_json
                FROM entries WHERE cache_key=?""",(identity[0],)).fetchone()
            if row is None or row[2]!=VERSION or row[1]<=checked or row[0]>checked+60:
                return None
            if hashlib.sha256(row[4].encode("utf-8")).hexdigest()!=row[3]:
                return None
            persisted=json.loads(row[4])
            def fetch_template(identifier):
                found=cx.execute("""SELECT content_json FROM product_line_templates
                    WHERE template_sha256=?""",(identifier,)).fetchone()
                return json.loads(found[0]) if found else None
            output=expand(persisted,fetch_template)
        if not _valid(request,output):
            return None
        output["cache"]={"state":"FRESH_CACHE","checked_at_utc":_iso(row[0]),
            "expires_at_utc":_iso(row[1]),"age_seconds":max(0,checked-row[0]),
            "origin":"AUTHENTICATED_SALESFORCE_UI","not_live":True,
            "schema_version":VERSION}
        return output
    except (OSError,sqlite3.DatabaseError,TypeError,ValueError,KeyError):
        return None


def live_meta(kind,now=None):
    t=int(time.time() if now is None else now)
    return {"state":"LIVE_SOURCE","checked_at_utc":_iso(t),
            "expires_at_utc":_iso(t+TTL_SECONDS[kind]),"age_seconds":0,
            "origin":"AUTHENTICATED_SALESFORCE_UI","not_live":False,
            "schema_version":VERSION}


def stats(now=None):
    t=int(time.time() if now is None else now)
    try:
        with _connect() as cx:
            allrows=cx.execute("""SELECT kind, observed_utc, expires_utc
                FROM entries WHERE schema_version=?""",(VERSION,)).fetchall()
        kinds={}
        for kind in TTL_SECONDS:
            rows=[r for r in allrows if r[0]==kind]
            fresh=[r for r in rows if r[2]>t and r[1]<=t+60]
            kinds[kind]={"fresh":len(fresh),"stale":len(rows)-len(fresh),
                         "last_checked_at_utc":_iso(max(x[1] for x in rows)) if rows else None}
        return {"status":"PASS","cache_status":"FRESH" if any(x["fresh"] for x in kinds.values()) else "EMPTY_OR_STALE",
                "tiers":kinds,"freshness_policy_seconds":TTL_SECONDS,
                "observed_at_utc":_iso(t),"local_only":True,
                "salesforce_write":False}
    except (OSError,sqlite3.DatabaseError,ValueError):
        return {"status":"BLOCK","code":"CACHE_UNAVAILABLE","local_only":True,"salesforce_write":False}


if __name__=="__main__":
    import sys
    if len(sys.argv)==2 and sys.argv[1]=="status":
        print(json.dumps(stats(),ensure_ascii=False))
    else:
        print(json.dumps({"status":"BLOCK","code":"CACHE_READONLY_STATUS_ONLY"}))
