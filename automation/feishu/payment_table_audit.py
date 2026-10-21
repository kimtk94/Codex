#!/usr/bin/env python3
"""Read-only audit of existing Payment Outstanding table in Feishu Base."""
import json
import os
import sys
import urllib.parse
from base_readonly_probe import request, require

TARGET = "Payment Outstanding 10.20"

def list_pages(path, token):
    cursor = ""
    seen = set()
    while True:
        qs = urllib.parse.urlencode({"page_size":100, **({"page_token":cursor} if cursor else {})})
        resp = request("GET", path+"?"+qs, token=token)
        if resp.get("code") != 0:
            raise RuntimeError("API_CODE_"+str(resp.get("code")))
        data = resp.get("data") or {}
        for item in data.get("items") or []:
            yield item
        if not data.get("has_more"):
            break
        nxt = data.get("page_token")
        if not nxt or nxt in seen:
            raise RuntimeError("Invalid pagination")
        seen.add(nxt)
        cursor = nxt

def field_readiness(fields):
    """Check candidate schema only. Presence is not a proof of paid status."""
    def normalize(v):
        return " ".join(str(v or "").casefold().replace("_", " ").replace("-", " ").split())
    available = {normalize(f.get("field_name")) for f in fields}
    aliases = {
        "invoice_id": ("invoice number", "invoice no", "invoice id", "erp invoice number", "cms invoice number", "e tax number", "세금계산서 번호"),
        "amount": ("invoice amount", "outstanding amount", "balance", "청구금액", "미수금"),
        "payment_evidence": ("payment date", "paid date", "payment amount", "paid amount", "remark payment status", "입금일", "입금액"),
    }
    return {k: any(normalize(a) in available for a in values) for k, values in aliases.items()}

def main():
    auth = request("POST","/open-apis/auth/v3/tenant_access_token/internal",
        body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    token = auth.get("tenant_access_token")
    if auth.get("code") != 0 or not token:
        raise RuntimeError("Authentication rejected")
    app = require("FEISHU_BASE_APP_TOKEN")
    prefix="/open-apis/bitable/v1/apps/"+urllib.parse.quote(app,safe="")
    tables=list(list_pages(prefix+"/tables",token))
    matches=[t for t in tables if t.get("name")==TARGET]
    print("AUTH: PASS",flush=True)
    print("BASE_TABLE_COUNT:",len(tables),flush=True)
    if len(matches)!=1:
        print("PAYMENT_TABLE_FOUND:",len(matches),flush=True)
        print("PAYMENT_AUDIT: BLOCKED_TARGET_TABLE_NOT_FOUND",flush=True)
        return 2
    table_id=matches[0]["table_id"]
    root=prefix+"/tables/"+urllib.parse.quote(table_id,safe="")
    fields=list(list_pages(root+"/fields",token))
    records=list(list_pages(root+"/records",token))
    identifiers=[r.get("record_id") for r in records]
    if not all(identifiers) or len(identifiers)!=len(set(identifiers)):
        raise RuntimeError("Missing/duplicate record IDs")
    found = field_readiness(fields)
    for key,value in found.items():
        print("PAYMENT_FIELD_"+key.upper()+"_PRESENT:",value)
    print("RECONCILIATION_READINESS:", "READY_FOR_MAPPING_REVIEW" if all(found.values()) else "MISSING_REQUIRED_FIELDS")
    print("PAYMENT_SETTLEMENT_PROOF: UNVERIFIED")
    # Do not print field names or customer record values.
    print("PAYMENT_TABLE_FOUND: 1")
    print("PAYMENT_TABLE_ID:",table_id)
    print("PAYMENT_FIELD_COUNT:",len(fields))
    # Schema metadata only: names are needed to map real invoice identifiers.
    # Customer record values and tokens are never printed.
    if os.getenv("FEISHU_AUDIT_FIELD_NAMES") == "1":
        print("PAYMENT_FIELD_NAMES:",json.dumps([f.get("field_name") for f in fields],ensure_ascii=False))
    print("PAYMENT_FIELD_TYPE_COUNTS:",json.dumps({str(t):sum(f.get("type")==t for f in fields)
       for t in sorted({f.get("type") for f in fields})},sort_keys=True))
    print("PAYMENT_RECORD_COUNT:",len(records))
    print("PAYMENT_AUDIT: PASS")
    print("WRITE_OPERATIONS: 0")
    return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc:
        print("PAYMENT_AUDIT_FAILED:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
