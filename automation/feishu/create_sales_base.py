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
def feishu_app_token(token):
    return "/open-apis/bitable/v1/apps/" + urllib.parse.quote(token, safe="")


def create_base(token):
    response = request("POST", "/open-apis/bitable/v1/apps", token=token,
                       body={"name": NAME, "time_zone": "Asia/Seoul"})
    if response.get("code") != 0:
        raise RuntimeError("FEISHU_BASE_CREATE_CODE_" + str(response.get("code")))
    data = (response.get("data") or {}).get("app") or {}
    app_token, url = data.get("app_token"), data.get("url")
    if not app_token or not url or not url.startswith("https://"):
        raise RuntimeError("FEISHU_CREATE_ID_URL_MISSING")
    return app_token, url


def create_missing_tables(token, app_token):
    prefix = feishu_app_token(app_token)
    resp = request("GET", prefix + "/tables?page_size=100", token=token)
    if resp.get("code") != 0:
        raise RuntimeError("FEISHU_NEW_BASE_TABLES_READ_CODE_" + str(resp.get("code")))
    item_names = [t.get("name") for t in ((resp.get("data") or {}).get("items") or [])]
    if (resp.get("data") or {}).get("has_more"):
        raise RuntimeError("NEW_BASE_UNEXPECTED_TABLE_PAGINATION")
    for name, fields in TABLES.items():
        if item_names.count(name) > 1:
            raise RuntimeError("DUPLICATE_NEW_BASE_TABLE_" + name.replace(" ", "_"))
        if name in item_names:
            print("TABLE_EXISTS=" + name)
            continue
        result = request("POST", prefix + "/tables", token=token,
                         body={"table": {
                             "name": name, "default_view_name": "All",
                             "fields": [{"field_name": field, "type": 1} for field in fields],
                         }})
        if result.get("code") != 0:
            raise RuntimeError("CREATE_TABLE_FAILED_" + name.replace(" ", "_") +
                               "_CODE_" + str(result.get("code")))
        # Feishu API responses can vary by table-creation response shape.
        # Confirm persistence via a new list instead of relying on nested IDs.
        check = request("GET", prefix + "/tables?page_size=100", token=token)
        if check.get("code") != 0:
            raise RuntimeError("NEW_TABLE_READBACK_FAILED_" + name.replace(" ", "_"))
        names_after = [item.get("name") for item in ((check.get("data") or {}).get("items") or [])]
        if names_after.count(name) != 1:
            raise RuntimeError("NEW_TABLE_MISSING_AFTER_CREATE_" + name.replace(" ", "_"))
        print("TABLE_CREATED=" + name)


def provision():
    existing = os.environ.get("FEISHU_SALES_BASE_APP_TOKEN", "").strip()
    if existing and existing != "PENDING":
        print("USING_EXISTING_NEW_BASE_TOKEN")
    elif existing != "PENDING":
        raise RuntimeError("NEW_BASE_BOOTSTRAP_GUARD_MISSING")
    credentials = request("POST", "/open-apis/auth/v3/tenant_access_token/internal", body={
        "app_id": require("FEISHU_APP_ID"), "app_secret": require("FEISHU_APP_SECRET"),
    })
    if credentials.get("code") != 0 or not credentials.get("tenant_access_token"):
        raise RuntimeError("FEISHU_AUTH_FAILED")
    token = credentials["tenant_access_token"]
    if existing == "PENDING":
        app_token, url = create_base(token)
        print("NEW_BASE_CREATED")
        print("BASE_URL=" + url)
    else:
        app_token = existing
    create_missing_tables(token, app_token)
    print("FEISHU_BASE_PROVISION_PASS tables=" + str(len(TABLES)))


if __name__ == "__main__":
    try:
        provision()
    except Exception as exc:
        # Only print safe error type/label, never access tokens or request contents.
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("FEISHU_BASE_PROVISION_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
