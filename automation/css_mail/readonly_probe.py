#!/usr/bin/env python3
"""Read-only Gmail health and volume probe for CSS automation.

Does not fetch bodies, attachments, customer addresses, or message subjects.
Does not send, draft, delete, or modify email.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_PAGES = 20


def request_json(url, method="GET", payload=None, token=None):
    data = urllib.parse.urlencode(payload).encode() if payload else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def access_token():
    values = {key: os.getenv(key, "").strip() for key in
              ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")}
    if any(not value for value in values.values()):
        raise RuntimeError("GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and GMAIL_REFRESH_TOKEN are required")
    info = request_json(TOKEN_ENDPOINT, "POST", {
        "client_id": values["GMAIL_CLIENT_ID"],
        "client_secret": values["GMAIL_CLIENT_SECRET"],
        "refresh_token": values["GMAIL_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    })
    if not info.get("access_token"):
        raise RuntimeError("OAuth refresh did not yield an access token")
    return info["access_token"]


def count_messages(token, query):
    total = 0
    token_page = None
    pages = 0
    truncated = False
    while True:
        params = {"q": query, "maxResults": 500, "fields": "nextPageToken,messages/id"}
        if token_page:
            params["pageToken"] = token_page
        url = GMAIL_ENDPOINT + "/messages?" + urllib.parse.urlencode(params)
        result = request_json(url, token=token)
        total += len(result.get("messages", []))
        pages += 1
        token_page = result.get("nextPageToken")
        if not token_page:
            break
        if pages >= MAX_PAGES:
            truncated = True
            break
    return {"count": total, "truncated": truncated}


def run():
    token = access_token()
    # Force identity/permission validation without logging email address.
    profile = request_json(GMAIL_ENDPOINT + "/profile", token=token)
    if "emailAddress" not in profile:
        raise RuntimeError("Unable to read Gmail profile")
    hours = int(os.getenv("CSS_MAIL_LOOKBACK_HOURS", "48"))
    if hours < 1 or hours > 168:
        raise RuntimeError("CSS_MAIL_LOOKBACK_HOURS must be between 1 and 168")
    after = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).timestamp())
    # Gmail 'after' is epoch seconds in this form; queries avoid timezone ambiguity.
    queries = {
        "inbox": "in:inbox after:" + str(after),
        "unread_inbox": "in:inbox is:unread after:" + str(after),
        "sent": "in:sent after:" + str(after),
    }
    result = {
        "status": "PASS",
        "mode": "READ_ONLY",
        "lookback_hours": hours,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "metrics": {name: count_messages(token, query) for name, query in queries.items()},
    }
    output = os.getenv("CSS_MAIL_REPORT_PATH", "css_mail_probe.json")
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print("CSS_MAIL_PROBE: PASS; mode=READ_ONLY; metrics=" +
          json.dumps(result["metrics"], separators=(",", ":")))


if __name__ == "__main__":
    try:
        run()
    except (RuntimeError, urllib.error.URLError, ValueError, KeyError) as error:
        # Suppress remote body and tokens in log.
        print("CSS_MAIL_PROBE: FAILED (" + type(error).__name__ + ")", file=sys.stderr)
        sys.exit(1)
