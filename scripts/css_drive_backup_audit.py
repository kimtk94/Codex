#!/usr/bin/env python3
"""Read-only inventory for Novogene CSS Drive backups. Never deletes or downloads DBs."""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

FOLDER = "14mOdogWGR274qysZlQktpg7mgwB8YnFw"
PATTERN = re.compile(r"^(mail_sync_fast|css_project_manager)_(\d{8})_(\d{6})\.sqlite3$")
SCOPE = ["https://www.googleapis.com/auth/drive.metadata.readonly"]


def access_token():
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    payload = os.environ.get("GCP_SA_JSON", "")
    if not payload:
        raise RuntimeError("Missing GCP_SA_JSON secret (service account JSON).")
    info = json.loads(payload)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPE)
    credentials.refresh(Request())
    return credentials.token


def list_all(token):
    page = None
    files = []
    while True:
        query = {
            "q": f"'{FOLDER}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,size,modifiedTime,mimeType)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page:
            query["pageToken"] = page
        url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)
        files.extend(data.get("files", []))
        page = data.get("nextPageToken")
        if not page:
            break
    return files


def main():
    files = list_all(access_token())
    now = dt.datetime.now(dt.timezone.utc)
    groups = collections.defaultdict(list)
    unknown = 0
    for f in files:
        match = PATTERN.fullmatch(f.get("name", ""))
        if match:
            groups[match.group(1)].append((f, match.group(2), match.group(3)))
        else:
            unknown += 1

    output = {"read_only": True, "timestamp_utc": now.isoformat(), "files_total": len(files),
              "unrecognized_files": unknown, "db_groups": {}}
    for name, rows in sorted(groups.items()):
        rows.sort(key=lambda r: (r[1], r[2]), reverse=True)
        unique_sizes = len(set(int(r[0].get("size", 0)) for r in rows))
        output["db_groups"][name] = {
            "count": len(rows),
            "total_gb_decimal": round(sum(int(r[0].get("size", 0)) for r in rows) / 1e9, 3),
            "latest_backup": rows[0][0]["name"] if rows else None,
            "distinct_file_sizes": unique_sizes,
            "same_size_is_not_proof_of_duplicate": True,
        }
    text = json.dumps(output, indent=2, ensure_ascii=False)
    print(text)
    path = os.environ.get("CSS_AUDIT_OUTPUT", "css_drive_backup_inventory.json")
    with open(path, "w", encoding="utf-8") as out:
        out.write(text + "\n")
    if not files:
        raise RuntimeError("No backup files visible. Verify Drive folder sharing/access.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"CSS Drive backup audit failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
