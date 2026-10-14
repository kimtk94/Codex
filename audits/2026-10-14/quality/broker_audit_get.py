"""Audit-only Toss GET client. No OAuth renewal, retries, files written, or order mutations.
Not for unattended live use; run only after explicit operational approval.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE="https://openapi.tossinvest.com"
PATHS={"holdings":"/api/v1/holdings","open_orders":"/api/v1/orders"}

def request_snapshot(cache_path, account, *, transport=None, now=None):
    if not account:
        return {"status":"BLOCKED","reason":"ACCOUNT_NOT_CONFIGURED"}
    current=time.time() if now is None else now
    try:
        # Open directly read-only; do not instantiate production TossClient.
        with Path(cache_path).open("r",encoding="utf-8") as h: token_doc=json.load(h)
        token=str(token_doc["access_token"])
        expiry=float(token_doc["expires_at"])
        if not token or expiry-current<=120:
            return {"status":"BLOCKED","reason":"TOKEN_EXPIRED_OR_NEAR_EXPIRY"}
    except (OSError,ValueError,TypeError,KeyError):
        return {"status":"BLOCKED","reason":"CACHE_UNAVAILABLE"}
    if transport is None:
        def transport(url,headers):
            req=urllib.request.Request(url,headers=headers,method="GET")
            with urllib.request.urlopen(req,timeout=10) as resp:
                if resp.status!=200: raise RuntimeError("UNEXPECTED_STATUS")
                return json.load(resp)
    headers={"Authorization":"Bearer "+token,"Accept":"application/json","X-Tossinvest-Account":account}
    out={}
    for name,path in PATHS.items():
        url=BASE+path
        if name=="open_orders": url+="?"+urllib.parse.urlencode({"status":"OPEN"})
        try:
            out[name]=transport(url,headers)
        except Exception:
            # Do not retry 401, do not invalidate shared token, and never log request headers.
            return {"status":"BLOCKED","reason":"BROKER_REQUEST_FAILED","completed_sections":list(out)}
    return {"status":"OK","payloads":out}
