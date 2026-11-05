#!/usr/bin/env python3
"""QQ IMAP -> isolated Feishu Base staging. Never mutates business tables or sends mail.

Modes: probe (read-only), smoke (isolated test record only), sync (smoke then append).
Customer values must never be printed or written to CI artifacts.
"""
import datetime as dt
import email
import hashlib
import html
from html.parser import HTMLParser
import imaplib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.parser import BytesParser
from email.policy import default

API_ROOT = "https://open.feishu.cn"
TABLE = "QQ Mail Intake"
FIELDS = (
    "Mail Key", "Message ID", "Folder", "Direction", "Received At",
    "From", "To", "CC", "Subject", "Body Excerpt", "AMEA", "H Project",
    "Captured UTC", "In Reply To",
)
SMOKE_KEY = "__QQ_FEISHU_SMOKE_V1__"
MAX_MESSAGE_BYTES = 262144


class SafeError(RuntimeError):
    pass


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SafeError("MISSING_CONFIGURATION:" + name)
    return value


def api(method, path, token=None, data=None, action="feishu_api"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        API_ROOT + path,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None,
        headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            obj = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SafeError(action + "_HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError):
        raise SafeError(action + "_NETWORK_ERROR") from None
    if obj.get("code") != 0:
        raise SafeError(action + "_CODE_" + str(obj.get("code", "UNKNOWN"))) from None
    # The auth endpoint returns tenant_access_token at the response root.
    # Other Bitable endpoints return their payload under "data".
    if path == "/open-apis/auth/v3/tenant_access_token/internal":
        return obj
    return obj.get("data") or {}


def list_all(path, token, action):
    rows = []
    cursor = ""
    for _ in range(1000):
        qs = urllib.parse.urlencode({"page_size": 100, **({"page_token": cursor} if cursor else {})})
        data = api("GET", path + "?" + qs, token, action=action)
        rows.extend(data.get("items") or [])
        if not data.get("has_more"):
            return rows
        next_cursor = data.get("page_token")
        if not next_cursor or next_cursor == cursor:
            raise SafeError(action + "_BAD_PAGINATION")
        cursor = next_cursor
    raise SafeError(action + "_PAGINATION_LIMIT")


def auth():
    data = api(
        "POST", "/open-apis/auth/v3/tenant_access_token/internal",
        data={"app_id": required("FEISHU_APP_ID"), "app_secret": required("FEISHU_APP_SECRET")},
        action="feishu_auth",
    )
    token = data.get("tenant_access_token")
    if not token:
        raise SafeError("FEISHU_AUTH_TOKEN_MISSING")
    base = required("FEISHU_BASE_APP_TOKEN")
    return token, "/open-apis/bitable/v1/apps/" + urllib.parse.quote(base, safe="")


def find_table(token, root):
    tables = list_all(root + "/tables", token, "table_list")
    matches = [x for x in tables if x.get("name") == TABLE]
    if len(matches) > 1:
        raise SafeError("DUPLICATE_STAGING_TABLE_NAME")
    if not matches:
        return None
    return matches[0].get("table_id")


def get_fields(token, table_path):
    return list_all(table_path + "/fields", token, "field_list")


def ensure_table(token, root):
    table_id = find_table(token, root)
    if table_id is None:
        # Creation is permitted only for this isolated table, never for existing business tables.
        created = api(
            "POST", root + "/tables", token,
            data={"table": {
                "name": TABLE, "default_view_name": "All",
                "fields": [{"field_name": name, "type": 1} for name in FIELDS],
            }},
            action="staging_table_create",
        )
        table_id = (created.get("table") or {}).get("table_id") or created.get("table_id")
        if not table_id:
            raise SafeError("CREATE_TABLE_ID_MISSING")
        print("STAGING_TABLE_CREATED")
    table_path = root + "/tables/" + urllib.parse.quote(table_id, safe="")
    fields = get_fields(token, table_path)
    types = {f.get("field_name"): f.get("type") for f in fields}
    if any(types.get(name) != 1 for name in FIELDS):
        raise SafeError("STAGING_SCHEMA_MISMATCH_NO_WRITES")
    return table_path


def plain_field(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(plain_field(item) for item in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("value") or "")
    return ""


def existing(token, table_path):
    records = list_all(table_path + "/records", token, "record_list")
    indexed = {}
    for item in records:
        row_id = item.get("record_id")
        key = plain_field((item.get("fields") or {}).get("Mail Key"))
        if key:
            if key in indexed or not row_id:
                raise SafeError("DUPLICATE_MAIL_KEYS_OR_IDS")
            indexed[key] = row_id
    return indexed


def write_record(token, table_path, row, row_id=None):
    path = table_path + "/records"
    if row_id:
        path += "/" + urllib.parse.quote(row_id, safe="")
        method = "PUT"
    else:
        method = "POST"
    result = api(method, path, token, data={"fields": row}, action="staging_record_write")
    record = result.get("record") or {}
    if not row_id and not record.get("record_id"):
        raise SafeError("STAGING_CREATE_NO_RECORD_ID")
    return record.get("record_id") or row_id


def smoke(token, table_path, indexed):
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    fields = {
        "Mail Key": SMOKE_KEY, "Subject": "Feishu mail sync connectivity test",
        "Direction": "SYSTEM", "Captured UTC": now,
    }
    row_id = write_record(token, table_path, fields, indexed.get(SMOKE_KEY))
    # Confirm committed record is visible to the writer identity.
    result = api(
        "GET", table_path + "/records/" + urllib.parse.quote(row_id, safe=""),
        token, action="smoke_readback",
    )
    back = result.get("record") or {}
    if plain_field((back.get("fields") or {}).get("Mail Key")) != SMOKE_KEY:
        raise SafeError("SMOKE_READBACK_MISMATCH")
    indexed[SMOKE_KEY] = row_id
    print("FEISHU_SMOKE_PASS")


def folders(im):
    status, entries = im.list()
    if status != "OK":
        raise SafeError("QQ_IMAP_LIST_FAILED")
    names = []
    for item in entries or []:
        m = re.search(r' (?:"([^"]+)"|([^ "]+))$', item.decode("utf-8", "replace"))
        if m:
            names.append((m.group(1) or m.group(2), item.decode("utf-8", "replace").lower()))
    sent = next((name for name, desc in names if "\\sent" in desc or name.lower() in
                 ("sent", "sent items", "sent messages")), None)
    if not sent:
        raise SafeError("QQ_SENT_FOLDER_UNRESOLVED")
    return (("INBOX", "INBOUND"), (sent, "OUTBOUND"))


def key(folder, uidvalidity, uid):
    return hashlib.sha256((folder + "|" + uidvalidity + "|" + uid).encode("utf-8")).hexdigest()


class HtmlToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fragments = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, text):
        if not self.skip:
            self.fragments.append(text)


def extract_body(msg):
    html_body = ""
    try:
        for part in msg.walk():
            if part.get_content_disposition() == "attachment" or part.get_filename():
                continue
            typ = part.get_content_type()
            if typ not in ("text/plain", "text/html"):
                continue
            try:
                payload = part.get_content()
            except (UnicodeError, LookupError, ValueError, AssertionError):
                continue
            if not isinstance(payload, str):
                continue
            if typ == "text/plain":
                return re.sub(r"\s+", " ", payload).strip()[:1800]
            if not html_body:
                html_body = payload
    except (ValueError, TypeError):
        pass
    if html_body:
        try:
            parser = HtmlToText()
            parser.feed(html_body)
            return re.sub(r"\s+", " ", html.unescape(" ".join(parser.fragments))).strip()[:1800]
        except (ValueError, TypeError):
            return ""
    return ""


def short(value, limit=1500):
    return str(value or "").strip()[:limit]


def address(value):
    from email.utils import getaddresses
    return ", ".join(a.lower() for _, a in getaddresses([str(value or "")]) if a)[:1000]


def date_string(value):
    try:
        return email.utils.parsedate_to_datetime(str(value)).isoformat()
    except (ValueError, TypeError, IndexError, OverflowError):
        return ""


def decode_mail(payload, folder, direction, uidvalidity, uid):
    msg = BytesParser(policy=default).parsebytes(payload)
    subject = short(msg.get("Subject"), 500)
    return {
        "Mail Key": key(folder, uidvalidity, uid), "Message ID": short(msg.get("Message-ID"), 300),
        "Folder": short(folder, 200), "Direction": direction,
        "Received At": date_string(msg.get("Date")), "From": address(msg.get("From")),
        "To": address(msg.get("To")), "CC": address(msg.get("Cc")),
        "Subject": subject, "Body Excerpt": extract_body(msg),
        "AMEA": ", ".join(sorted(set(re.findall(r"AMEA\d{7,}", subject, re.I)))),
        "H Project": ", ".join(sorted(set(re.findall(r"\bH[- ]?(?:\d{5,}|\d{2,}[A-Z]{1,4}\d{3,})\b", subject, re.I)))),
        "Captured UTC": dt.datetime.now(dt.timezone.utc).isoformat(),
        "In Reply To": short(msg.get("In-Reply-To"), 300),
    }


def select_uids(unseen, cap):
    # Prioritize the freshest half while gradually backfilling older unmatched records.
    recent = unseen[-(cap // 2):]
    older = [u for u in unseen if u not in set(recent)]
    return older[:cap - len(recent)] + recent


def collect_from_imap(im, indexed, max_per_folder, scan_days, since_date=None, min_date_kst=None):
    incoming = []
    cutoff_skipped = 0
    for folder, direction in folders(im):
        status, _ = im.select('"' + folder.replace('"', "") + '"', readonly=True)
        if status != "OK":
            raise SafeError("QQ_IMAP_SELECT_FAILED")
        status, validity = im.response("UIDVALIDITY")
        if not validity or not validity[0]:
            raise SafeError("QQ_UIDVALIDITY_MISSING")
        uidvalidity = validity[0].decode("ascii", "replace")
        since = since_date or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=scan_days)).strftime("%d-%b-%Y")
        status, data = im.uid("SEARCH", None, "SINCE", since)
        if status != "OK":
            raise SafeError("QQ_IMAP_SEARCH_FAILED")
        uids = (data[0] or b"").split()
        missed = [uid for uid in uids if key(folder, uidvalidity, uid.decode("ascii")) not in indexed]
        selected = select_uids(missed, max_per_folder)
        print("QQ_FOLDER_SCAN direction=" + direction + " pending=" + str(len(missed)) +
              " selected=" + str(len(selected)))
        for uid in selected:
            # Bounded prefix includes MIME headers; never mark mail as read or move it.
            status, parts = im.uid("FETCH", uid, "(BODY.PEEK[]<0." + str(MAX_MESSAGE_BYTES) + ">)")
            if status != "OK":
                raise SafeError("QQ_IMAP_FETCH_FAILED")
            payload = next((part[1] for part in (parts or [])
                            if isinstance(part, tuple) and isinstance(part[1], bytes)), None)
            if payload is None:
                raise SafeError("QQ_IMAP_FETCH_EMPTY")
            row = decode_mail(payload, folder, direction, uidvalidity, uid.decode("ascii"))
            if min_date_kst is not None:
                from mail_classification_2026 import since_2026
                if not since_2026(row.get("Received At")):
                    cutoff_skipped += 1
                    continue
            incoming.append(row)
    if since_date is not None:
        print("QQ_2026_CUTOFF_SKIPPED="+str(cutoff_skipped))
    return incoming


def allocate_2026_quotas(pending_by_folder, limit):
    """Proportionally allocate one TOTAL per-run budget across Inbox and Sent.

    A sent folder with fewer messages cannot strand unused budget in a
    per-folder 1,500-message cap; remaining budget goes to the busy Inbox.
    Deterministic largest-remainder allocation, bounded by available mail.
    """
    counts = [max(0, int(n)) for n in pending_by_folder]
    budget = min(limit, sum(counts))
    if budget < 1:
        return [0 for _ in counts]
    total = sum(counts)
    raw = [budget * n / total for n in counts]
    quotas = [min(n, int(part)) for n,part in zip(counts,raw)]
    remaining = budget - sum(quotas)
    for i in sorted(range(len(counts)), key=lambda i:(-(raw[i]-int(raw[i])), -counts[i], i)):
        if not remaining:
            break
        if quotas[i] < counts[i]:
            quotas[i] += 1
            remaining -= 1
    if remaining:
        # Defensive fallback for future deployments with more folders.
        for i in range(len(counts)):
            extra = min(remaining, counts[i]-quotas[i])
            quotas[i] += extra
            remaining -= extra
            if not remaining:
                break
    if sum(quotas) != budget:
        raise SafeError("QQ_2026_ALLOCATION_MISMATCH")
    return quotas


def collect_2026_total(im, indexed, max_total):
    """Scan each folder once for UID allocation, then fetch selected messages.

    IMAP SINCE uses the preceding UTC calendar day because final 2026 cutoff
    must use each parsed message's timezone-aware Date header in Asia/Seoul.
    """
    folder_scans = []
    for folder, direction in folders(im):
        status, _ = im.select('"' + folder.replace('"', "") + '"', readonly=True)
        if status != "OK":
            raise SafeError("QQ_2026_SELECT_FAILED")
        status, validity = im.response("UIDVALIDITY")
        if not validity or not validity[0]:
            raise SafeError("QQ_2026_UIDVALIDITY_MISSING")
        uv = validity[0].decode("ascii", "replace")
        status, data = im.uid("SEARCH", None, "SINCE", "31-Dec-2025")
        if status != "OK":
            raise SafeError("QQ_2026_SEARCH_FAILED")
        raw_uids = (data[0] or b"").split()
        missed = [uid for uid in raw_uids
                  if key(folder, uv, uid.decode("ascii")) not in indexed]
        folder_scans.append((folder, direction, uv, missed))
    quotas = allocate_2026_quotas([len(pending) for _,_,_,pending in folder_scans], max_total)
    print("QQ_2026_BATCH_BUDGET="+str(max_total)+" allocated="+str(sum(quotas)))
    incoming = []
    skipped = 0
    from mail_classification_2026 import since_2026
    for (folder, direction, uv, missed), quota in zip(folder_scans, quotas):
        selected = select_uids(missed, quota)
        print("QQ_FOLDER_SCAN direction="+direction+" pending="+str(len(missed))+
              " selected="+str(len(selected)))
        if not selected:
            continue
        status, _ = im.select('"' + folder.replace('"', "") + '"', readonly=True)
        if status != "OK":
            raise SafeError("QQ_2026_FETCH_SELECT_FAILED")
        # Refuse if folder identity changed between SEARCH and FETCH.
        _, validity = im.response("UIDVALIDITY")
        if not validity or validity[0].decode("ascii", "replace") != uv:
            raise SafeError("QQ_2026_FOLDER_UIDVALIDITY_CHANGED")
        for uid in selected:
            status, parts = im.uid("FETCH", uid, "(BODY.PEEK[]<0." + str(MAX_MESSAGE_BYTES) + ">)")
            if status != "OK":
                raise SafeError("QQ_2026_FETCH_FAILED")
            payload = next((part[1] for part in (parts or [])
                            if isinstance(part,tuple) and isinstance(part[1],bytes)), None)
            if payload is None:
                raise SafeError("QQ_2026_FETCH_EMPTY")
            row = decode_mail(payload, folder, direction, uv, uid.decode("ascii"))
            if not since_2026(row.get("Received At")):
                skipped += 1
                continue
            incoming.append(row)
    if len(incoming) > max_total:
        raise SafeError("QQ_2026_BATCH_OVER_BUDGET")
    print("QQ_2026_CUTOFF_SKIPPED="+str(skipped))
    print("QQ_2026_SELECTED_VALID="+str(len(incoming)))
    return incoming


def run(mode):
    if mode not in ("probe", "smoke", "sync", "backfill2026"):
        raise SafeError("INVALID_MODE")
    # Validate all required secrets before side effects.
    mail_user = required("CSS_QQ_MAIL_ADDRESS")
    mail_pass = required("CSS_QQ_MAIL_AUTH_CODE")
    token, base = auth()
    table_id = find_table(token, base)
    with imaplib.IMAP4_SSL("imap.exmail.qq.com", 993, timeout=40) as im:
        if im.login(mail_user, mail_pass)[0] != "OK":
            raise SafeError("QQ_LOGIN_FAILED")
        folders(im)
        print("QQ_MAIL_AUTH_PASS")
        print("FEISHU_AUTH_PASS")
        if mode == "probe":
            print("STAGING_TABLE_EXISTS=" + str(bool(table_id)))
            print("PROBE_PASS_WRITES_0")
            return
        table_path = ensure_table(token, base)
        indexed = existing(token, table_path)
        # Smoke writes are deliberately reserved for explicit smoke mode.
        # Scheduled ingestion must not mutate the synthetic test row each run.
        if mode == "smoke":
            smoke(token, table_path, indexed)
            print("SMOKE_ONLY_CUSTOMER_RECORD_WRITES_0")
            return
        backfill = mode == "backfill2026"
        days = min(max(1, int(os.environ.get("FEISHU_MAIL_SCAN_DAYS", "30"))), 60)
        if backfill:
            # One invocation, at most 3,000 messages TOTAL, allocated across
            # Inbox/Sent by pending counts (not 3,000 per folder).
            total_limit = min(max(1,int(os.environ.get("FEISHU_MAIL_BACKFILL_TOTAL", "3000"))),3000)
            new_rows = collect_2026_total(im,indexed,total_limit)
        else:
            cap = min(max(1,int(os.environ.get("FEISHU_MAIL_BATCH_PER_FOLDER", "45"))),100)
            new_rows = collect_from_imap(im,indexed,cap,days)
        added = 0
        if backfill:
            # Feishu batch API reduces thousands of individual API writes.
            for offset in range(0, len(new_rows), 25):
                batch = [r for r in new_rows[offset:offset+25] if r["Mail Key"] not in indexed]
                if not batch:
                    continue
                result = api("POST", table_path+"/records/batch_create", token,
                             data={"records":[{"fields":r} for r in batch]},
                             action="qq_2026_batch_create")
                created = result.get("records") or []
                if len(created) != len(batch) or any(not item.get("record_id") for item in created):
                    raise SafeError("QQ_2026_BATCH_CREATE_UNVERIFIED")
                # Verified API create response; subsequent retries of the job
                # reindex already-created Mail Keys, so partial runs are safe.
                for row, record in zip(batch, created):
                    indexed[row["Mail Key"]] = record["record_id"]
                added += len(batch)
                if added % 250 == 0 or added == len(new_rows):
                    print("QQ_2026_PROGRESS_ADDED="+str(added)+
                          " target="+str(len(new_rows)))
                time.sleep(0.25)  # Avoid Feishu batch-write rate limits.
        else:
            for row in new_rows:
                mail_key = row["Mail Key"]
                if mail_key in indexed:
                    continue
                indexed[mail_key] = write_record(token, table_path, row)
                added += 1
        print("FEISHU_MAIL_SYNC_PASS added=" + str(added) + " scanned=" + str(len(new_rows)))
        print("OTHER_FEISHU_TABLE_WRITES=0 EXTERNAL_MAIL_SENDS=0")
        im.logout()


if __name__ == "__main__":
    try:
        run(os.environ.get("FEISHU_MAIL_MODE", "probe"))
    except (SafeError, ValueError, imaplib.IMAP4.error) as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("FEISHU_MAIL_SYNC_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print("FEISHU_MAIL_SYNC_FAILED:" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
