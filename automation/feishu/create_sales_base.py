#!/usr/bin/env python3
"""One-time provisioning of a NEW, isolated Feishu Base for Novogene sales.

App token is a document identifier, not an API credential. Persist it in GitHub
Actions variables after validating write access, never in source or artifacts.
Existing Feishu Base is never modified.
"""
import json
import os
import sys
import urllib.error
import urllib.request
import urllib.parse

from base_readonly_probe import request, require
from qq_mail_ingest import FIELDS as MAIL_FIELDS

NAME = "Novogene Sales Workspace 2026"
VAR = "FEISHU_SALES_BASE_APP_TOKEN"
URL_VAR = "FEISHU_SALES_BASE_URL"

TABLES = {
    "QQ Mail Intake": tuple(MAIL_FIELDS),
    "Accounts": ("Account Name", "Institution", "Shipping Address", "Region", "Owner", "SFDC Account ID", "Last Sync UTC"),
    "Contacts": ("Contact Name KR", "Contact Name EN", "Email", "Account Name", "Job Function", "Academic Role", "SFDC Contact ID", "Sync To CDMS", "Last Sync UTC"),
    "Opportunities": ("Opportunity ID", "Contact Name KR", "Account", "Service", "Quantity", "Amount KRW Ex VAT", "Stage", "Source", "Last Sync UTC"),
    "Quotes": ("Quote ID", "Opportunity ID", "Contact", "Service", "Quantity", "Unit", "Amount KRW Ex VAT", "Country", "Currency", "Status"),
    "Projects": ("Project ID", "Contact", "Account", "Service", "Quantity", "Stage", "Expected Completion Month", "Forecast Basis", "Last Sync UTC"),
    "Revenue": ("Project ID", "Account", "Service", "Invoice Number", "Category Actual Pending Forecast", "Revenue KRW Ex VAT", "Revenue K USD", "Tax Invoice KRW Incl VAT", "Revenue Month", "Deduplication Key", "Source"),
}
API_ROOT = "https://api.github.com/repos/" + os.environ.get("GITHUB_REPOSITORY", "kimtk94/Codex")


def gh(method, endpoint, data=None, allow404=False):
    headers = {
        "Authorization": "Bearer " + require("GITHUB_TOKEN"),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "feishu-base-provisioner",
    }
    payload = json.dumps(data).encode() if data is not None else None
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API_ROOT + endpoint, headers=headers, data=payload, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp) if resp.status != 204 else {}
    except urllib.error.HTTPError as exc:
        if allow404 and exc.code == 404:
            return None
        raise RuntimeError("GITHUB_VARIABLE_API_HTTP_" + str(exc.code)) from None


def var_get(name):
    obj = gh("GET", "/actions/variables/" + name, allow404=True)
    return obj.get("value") if obj else None


def var_add(name, value):
    gh("POST", "/actions/variables", {"name": name, "value": value})


def var_update(name, value):
    gh("PATCH", "/actions/variables/" + name, {"name": name, "value": value})


def provision():
    old = var_get(VAR)
    if old and old != "PENDING":
        print("BASE_ALREADY_PROVISIONED")
        print("BASE_URL=" + str(var_get(URL_VAR) or "REGISTERED_NO_URL"))
        return
    if old == "PENDING":
        raise RuntimeError("BASE_BOOTSTRAP_PENDING_REVIEW_REQUIRED")
    # Verify ability to persist the app token *before* creating a new Feishu document.
    var_add(VAR, "PENDING")
    print("GITHUB_VARIABLE_WRITE_PREFLIGHT_PASS")
    credentials = request("POST", "/open-apis/auth/v3/tenant_access_token/internal", body={
        "app_id": require("FEISHU_APP_ID"), "app_secret": require("FEISHU_APP_SECRET"),
    })
    if credentials.get("code") != 0 or not credentials.get("tenant_access_token"):
        raise RuntimeError("FEISHU_AUTH_FAILED")
    token = credentials["tenant_access_token"]
    result = request("POST", "/open-apis/bitable/v1/apps", token=token,
                     body={"name": NAME, "time_zone": "Asia/Seoul"})
    if result.get("code") != 0:
        raise RuntimeError("FEISHU_BASE_CREATE_CODE_" + str(result.get("code")))
    base = (result.get("data") or {}).get("app") or {}
    app_token = base.get("app_token")
    url = base.get("url")
    if not app_token or not url or not url.startswith("https://"):
        raise RuntimeError("FEISHU_BASE_CREATE_MISSING_ID_URL")
    # Store immediately after creation, before adding tables (partial recovery safe).
    var_update(VAR, app_token)
    var_add(URL_VAR, url)
    print("NEW_BASE_CREATED")
    print("BASE_URL=" + url)
    prefix = "/open-apis/bitable/v1/apps/" + urllib.parse.quote(app_token, safe="")
    # This is a brand-new Base. Do not touch the existing business Base.
    for name, fields in TABLES.items():
        table = request("POST", prefix + "/tables", token=token,
                        body={"table": {
                            "name": name, "default_view_name": "All",
                            "fields": [{"field_name": field, "type": 1} for field in fields],
                        }})
        if table.get("code") != 0:
            raise RuntimeError("CREATE_TABLE_FAILED_" + name.replace(" ", "_") +
                               "_CODE_" + str(table.get("code")))
        table_id = ((table.get("data") or {}).get("table") or {}).get("table_id")
        if not table_id:
            raise RuntimeError("CREATE_TABLE_ID_MISSING_" + name.replace(" ", "_"))
        print("TABLE_CREATED=" + name)
    print("FEISHU_BASE_PROVISION_PASS tables=" + str(len(TABLES)))


if __name__ == "__main__":
    try:
        provision()
    except Exception as exc:
        # Only print safe error type/label, never access tokens or request contents.
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("FEISHU_BASE_PROVISION_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
