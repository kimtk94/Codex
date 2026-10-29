#!/usr/bin/env python3
"""Publish ONLY four parallel QA job statuses, never business data or decisions."""
import base64
import datetime as dt
import json
import os
import sys
from urllib.parse import quote

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TITLE = "Parallel Track Status"
HEADERS = ["Track", "Result", "Checked KST", "GitHub Run", "Checked Scope", "Boundary", "Run Number"]
TRACKS = (
    ("A · SFDC Report / Lead", "TRACK_A_RESULT",
     "Latest SFDC Lead/Oppo/Quote, exact-personal sent evidence, NBA parity",
     "Read-only: no SFDC or QQ writes"),
    ("B · Revenue", "TRACK_B_RESULT",
     "Invoice + verified Pending + Forecast, FX and offline revenue tests",
     "Read-only: no billing/invoice edits"),
    ("C · SFDC Desktop", "TRACK_C_RESULT",
     "Mocked UI/lookup/identity tests from isolated SFDC branch",
     "No live SFDC login, no Save"),
    ("D · Web Dashboard", "TRACK_D_RESULT",
     "Node personal Lead projection tests and API syntax",
     "No authenticated browser E2E"),
)
ALLOWED = {"success", "failure", "skipped", "cancelled"}


def api(method, uri, data=None):
    response = SESSION.request(method, "https://sheets.googleapis.com/v4/spreadsheets/" + BOOK + uri,
                               json=data, timeout=40)
    response.raise_for_status()
    return response.json() if response.content else {}


def range_path(a1):
    return "/values/" + quote("'" + TITLE + "'!" + a1, safe="")


def main():
    raw = os.environ.get("CKD_DRIVE_SA_JSON", "")
    if not raw:
        raise RuntimeError("MISSING_SHEET_CREDENTIAL")
    try:
        info = json.loads(raw)
    except ValueError:
        info = json.loads(base64.b64decode(raw))
    global SESSION
    SESSION = AuthorizedSession(service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    statuses = [os.environ.get(env, "") for _, env, _, _ in TRACKS]
    if any(value not in ALLOWED for value in statuses):
        raise ValueError("INVALID_TRACK_RESULT")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    number = os.environ.get("GITHUB_RUN_NUMBER", "")
    if not run_id.isdigit() or repo != "kimtk94/Codex":
        raise ValueError("INVALID_GITHUB_RUN_CONTEXT")
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    url = "https://github.com/" + repo + "/actions/runs/" + run_id
    meta = api("GET", "?fields=sheets.properties(title,sheetId,gridProperties.rowCount)")
    existing = [x["properties"] for x in meta.get("sheets", []) if x["properties"]["title"] == TITLE]
    if not existing:
        body = {"requests": [{"addSheet": {"properties": {
            "title": TITLE, "gridProperties": {"rowCount": 1000, "columnCount": 7,
            "frozenRowCount": 1, "hideGridlines": True}}}}]}
        res = api("POST", ":batchUpdate", body)
        sheet = res["replies"][0]["addSheet"]["properties"]
        sheet_id = sheet["sheetId"]
    else:
        sheet_id = existing[0]["sheetId"]
    rows = [[label, result.upper(), now, url, scope, boundary, number]
            for (label, _, scope, boundary), result in zip(TRACKS, statuses)]
    api("PUT", range_path("A1:G5") + "?valueInputOption=RAW",
        {"values": [HEADERS] + rows})
    # Independent readback of the actual statuses. Fail the publishing job if wrong.
    got = api("GET", range_path("A1:G5"))
    actual = got.get("values", [])
    if len(actual) != 5 or [r[1] for r in actual[1:]] != [x.upper() for x in statuses]:
        raise ValueError("TRACK_RESULT_READBACK_FAILED")
    # Latest summary is deterministic. History append is best-effort idempotent
    # and never changes any manual decision, original source, or client email.
    prev = api("GET", range_path("A8:G1000")).get("values", [])
    if not any(len(r) >= 4 and r[3] == url for r in prev):
        api("POST", range_path("A8:G1000") + ":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            {"values": rows})
    print("PARALLEL_TRACK_STATUS_PUBLISHED=4 READBACK_VERIFIED=true "
          + "PASSED=" + str(statuses.count("success"))
          + " FAILED=" + str(statuses.count("failure")) + " GID=" + str(sheet_id))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("TRACK_STATUS_PUBLISH_FAILED=" + type(e).__name__ + ":" + str(e).split("\n")[0],
              file=sys.stderr)
        sys.exit(1)
