#!/usr/bin/env python3
"""One-time, narrow Bitable owner-app grant to an individual Feishu email.

No public-link visibility changes, no ownership transfer, no data writes.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_TOKEN="IpMkbUD0vaFqtYs93a3csXtdn1b"
ALLOW_EMAIL="taehoon.kim@novogene.com"
OPENAPI="https://open.feishu.cn/open-apis"

class GrantError(RuntimeError):
    pass

def api(method,url,token=None,body=None):
    raw=None if body is None else json.dumps(body,ensure_ascii=False).encode("utf-8")
    hdr={"Content-Type":"application/json"}
    if token:hdr["Authorization"]="Bearer "+token
    try:
        with urllib.request.urlopen(urllib.request.Request(
            url,data=raw,headers=hdr,method=method),timeout=35) as response:
            payload=json.load(response)
    except urllib.error.HTTPError as e:
        raise GrantError("FEISHU_HTTP_"+str(e.code)) from None
    except (ValueError,OSError) as e:
        raise GrantError("FEISHU_NETWORK_OR_INVALID_RESPONSE_"+type(e).__name__) from None
    if not isinstance(payload,dict) or payload.get("code")!=0:
        raise GrantError("FEISHU_API_CODE_"+str(payload.get("code") if isinstance(payload,dict) else "INVALID"))
    return payload

def grant_plan(base,email):
    if base!=BASE_TOKEN:
        raise GrantError("UNAUTHORIZED_BASE_TOKEN")
    email=(email or "").strip().lower()
    if email!=ALLOW_EMAIL:
        raise GrantError("UNAUTHORIZED_EDITOR_EMAIL")
    return {
        "member_type":"email",
        "member_id":email,
        "perm":"edit"
    }

def classify_existing(members,editor_email):
    matches=[m for m in members if m.get("member_type")=="email" and
             str(m.get("member_id") or "").strip().lower()==editor_email]
    if len(matches)>1:
        raise GrantError("DUPLICATE_EDITOR_MEMBERSHIP")
    return matches[0] if matches else None

def run():
    grant=grant_plan(os.environ.get("FEISHU_BASE_APP_TOKEN"),os.environ.get("FEISHU_EDITOR_EMAIL"))
    if os.environ.get("FEISHU_SHARE_APPLY")!="1":
        raise GrantError("EXPLICIT_SHARE_APPLY_REQUIRED")
    app_id=os.environ.get("FEISHU_APP_ID")
    secret=os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not secret:
        raise GrantError("MISSING_APP_CREDENTIALS")
    auth=api("POST",OPENAPI+"/auth/v3/tenant_access_token/internal",body={
        "app_id":app_id,"app_secret":secret,
    })
    access=(auth.get("tenant_access_token") or "").strip()
    if not access:
        raise GrantError("EMPTY_TENANT_ACCESS_TOKEN")
    path=OPENAPI+"/drive/v1/permissions/"+BASE_TOKEN+"/members"
    existing=api("GET",path+"?type=bitable",token=access)
    members=(existing.get("data") or {}).get("items") or []
    if not isinstance(members,list):
        raise GrantError("PERMISSION_MEMBERS_INVALID_RESPONSE")
    old=classify_existing(members,grant["member_id"])
    if old and old.get("perm") in ("edit","full_access"):
        print("FEISHU_EDITOR_ACCESS_ALREADY_PRESENT=1",flush=True)
        return
    if old:
        member_id=urllib.parse.quote(grant["member_id"],safe="")
        uri=(path+"/"+member_id+"?type=bitable&member_type=email&need_notification=true")
        api("PUT",uri,token=access,body={"perm":"edit"})
        print("FEISHU_EDITOR_PERMISSION_UPGRADE_API_PASS=1",flush=True)
    else:
        outcome=api("POST",path+"?type=bitable&need_notification=true",token=access,body=grant)
        returned=(outcome.get("data") or {}).get("member") or {}
        if returned.get("perm") not in ("edit","full_access"):
            raise GrantError("EDITOR_CREATE_RESPONSE_NOT_EDIT")
        print("FEISHU_EDITOR_PERMISSION_CREATE_API_PASS=1",flush=True)
    # Always read the current member list; the API may return a normalized
    # openid rather than email, so do not claim exact-email readback from it.
    after=api("GET",path+"?type=bitable",token=access)
    items=(after.get("data") or {}).get("items")
    if not isinstance(items,list):
        raise GrantError("EDITOR_PERMISSION_READBACK_UNAVAILABLE")
    print("FEISHU_EDITOR_PERMISSION_LIST_READABLE=1",flush=True)
    print("FEISHU_SHARE_SCOPE=EXACT_SINGLE_BITABLE_EDITOR public_link_unchanged=true",flush=True)

if __name__=="__main__":
    try:
        run()
    except Exception as exc:
        print("FEISHU_EDITOR_GRANT_FAILED="+(
            str(exc) if isinstance(exc,GrantError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
