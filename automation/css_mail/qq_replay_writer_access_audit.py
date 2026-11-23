#!/usr/bin/env python3
"""Read-only, aggregate Drive permission audit for the existing CSS source.

This is not a lock and does not grant QQ stage replay authority. The current
CSS file has multiple editors; no GitHub Actions concurrency group can exclude
other Google Drive editors or direct Sheets clients.

Never print file IDs, permission IDs, email addresses, service account
identities, API payloads, exception text, or customer metadata.
"""
from collections import Counter
import json
import os
import re

BASELINE = {
    "owner": 1,
    "writer": 3,
    "reader": 0,
    "service_writers": 2,
}
EDIT_ROLES = {"owner", "writer", "organizer", "fileOrganizer"}
KNOWN_ROLES = EDIT_ROLES | {"reader", "commenter"}
KNOWN_TYPES = {"user", "group", "domain", "anyone"}


def _hold(reason, **counts):
    output = {
        "status": "HOLD",
        "reason_code": reason,
        "permission_entries": 0,
        "owner_count": 0,
        "writer_count": 0,
        "service_account_editor_count": 0,
        "public_or_domain_grants": 0,
        "group_grants": 0,
        "editor_count": 0,
        "count_baseline_matched": 0,
        "identity_allowlist_verified": 0,
        "all_external_writers_excluded": 0,
        "readback_proves_no_concurrent_writer": 0,
        "case_approvals_authenticated": 0,
        "qq_stage_writes": 0,
        "qq_cursor_writes": 0,
        "qq_canonical_writes": 0,
        "can_execute_replay": False,
    }
    output.update(counts)
    return output


def analyze_permissions(permissions):
    """Never infer exclusivity, even if counts equal an old snapshot."""
    if not isinstance(permissions, list) or not permissions:
        return _hold("PERMISSION_INVENTORY_UNAVAILABLE")
    if len(permissions) > 1000:
        return _hold("PERMISSION_INVENTORY_TOO_LARGE")
    roles = Counter()
    types = Counter()
    ids = set()
    sa_writers = 0
    incomplete = False
    for item in permissions:
        if not isinstance(item, dict):
            return _hold("PERMISSION_ENTRY_INVALID")
        pid = item.get("id")
        role = item.get("role")
        typ = item.get("type")
        if not isinstance(pid, str) or not pid or pid in ids:
            incomplete = True
        else:
            ids.add(pid)
        if role not in KNOWN_ROLES or typ not in KNOWN_TYPES:
            incomplete = True
        if item.get("deleted") is True:
            incomplete = True
        roles[role] += 1
        types[typ] += 1
        if role in EDIT_ROLES and typ == "user":
            email = item.get("emailAddress")
            if not isinstance(email, str) or "@" not in email:
                incomplete = True
            elif email.lower().endswith(".gserviceaccount.com"):
                sa_writers += 1
    owners = roles["owner"]
    editors = sum(roles[k] for k in EDIT_ROLES)
    baseline_matches = (
        owners == BASELINE["owner"]
        and roles["writer"] == BASELINE["writer"]
        and roles["reader"] == BASELINE["reader"]
        and sa_writers == BASELINE["service_writers"]
        and len(permissions) == 4
        and types["user"] == 4
    )
    exposure = types["anyone"] + types["domain"]
    groups = types["group"]
    if incomplete or owners != 1:
        reason = "PERMISSION_INVENTORY_INCOMPLETE"
    elif exposure or groups:
        reason = "EXPANDED_PERMISSION_SURFACE"
    elif not baseline_matches:
        reason = "PERMISSION_COUNT_DRIFT"
    else:
        reason = "KNOWN_MULTI_WRITER_HOLD"
    return _hold(
        reason,
        permission_entries=len(permissions),
        owner_count=owners,
        writer_count=roles["writer"],
        service_account_editor_count=sa_writers,
        public_or_domain_grants=exposure,
        group_grants=groups,
        editor_count=editors,
        count_baseline_matched=int(baseline_matches and not incomplete),
    )


def fetch_permissions(session, file_id):
    """Drive v3 GET permission pages, redirects forbidden, bounded coverage."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", str(file_id or "")):
        raise ValueError("SOURCE_FILE_ID_INVALID")
    url = "https://www.googleapis.com/drive/v3/files/" + file_id + "/permissions"
    token = None
    visited = set()
    items = []
    for _ in range(10):
        params = {
            "supportsAllDrives": "true",
            "pageSize": 100,
            "fields": ("nextPageToken,"
                       "permissions(id,type,role,emailAddress,domain,"
                       "deleted,allowFileDiscovery)"),
        }
        if token:
            params["pageToken"] = token
        response = session.get(url, params=params, timeout=30,
                               allow_redirects=False)
        if not (200 <= response.status_code < 300):
            raise ValueError("SOURCE_PERMISSION_READ_FAILED")
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("permissions"), list):
            raise ValueError("SOURCE_PERMISSION_RESPONSE_INVALID")
        items.extend(data["permissions"])
        token = data.get("nextPageToken")
        if token in ("", None):
            return items
        if not isinstance(token, str) or token in visited or len(items) > 1000:
            raise ValueError("SOURCE_PERMISSION_PAGINATION_UNSAFE")
        visited.add(token)
    raise ValueError("SOURCE_PERMISSION_PAGINATION_UNBOUNDED")


def main():
    source_id = (os.getenv("CSS_SHEET_ID") or "").strip()
    credential = (os.getenv("CKD_DRIVE_SA_JSON") or "").strip()
    if not source_id or not credential:
        result = _hold("PERMISSION_AUDIT_NOT_CONFIGURED")
    else:
        try:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            info = json.loads(credential)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"]
            )
            session = AuthorizedSession(creds)
            result = analyze_permissions(fetch_permissions(session, source_id))
        except Exception:
            # Omit exception text: it can contain a file ID, principal or token.
            result = _hold("PERMISSION_AUDIT_UNAVAILABLE")
    print("QQ_WRITER_ACCESS_AUDIT=" + json.dumps(result, sort_keys=True))
    # A successful inspection is not a positive financial execution gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
