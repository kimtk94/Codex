#!/usr/bin/env python3
"""2026 QQ mail -> Account/Contact/Project identity evidence in NEW Feishu Base.

Mail records: direct Feishu QQ Mail Intake, never Google Sheets.
Legacy SFDC Contacts, Leads, Quote Export and CSS Project Dashboard: read-only
matching references, explicitly labelled as such, never authoritative new events.
No name-only matching, no inference of invoice payment, no outgoing mail or SFDC writes.
"""
import collections
import datetime as dt
import os
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

from qq_mail_ingest import SafeError, api, auth, find_table, list_all, plain_field, SMOKE_KEY
from mail_classification_2026 import classify, email_set, since_2026, PROJECTS, CSS
from qq_mail_feed_periods import segment, parse_aware
from setup_sales_web import BASE_URL, EXPECTED_BASE, field_map, filter_matches, get_view, resolve_view
from sales_metrics_sync import req_sheet, sheets_session, CSS_SHEET, UNIFIED_SHEET

KST = ZoneInfo("Asia/Seoul")
TABLE = "Mail Identity 2026"
SCHEMA = (
    "Mail Key", "Received KST", "Feed Lane", "Direction", "Subject",
    "Primary Category", "Milestone", "Account", "Account ID",
    "Contact", "Contact ID", "Project ID", "H Project", "Opportunity ID",
    "Contact Link", "Project Link", "Relationship Status", "Review State",
    "Evidence", "Owner Evidence", "Reference Basis", "Last Sync KST",
    "Classification Tags", "Rule Version", "Classification Evidence",
    "Mail Role", "Followup Pool", "Evidence Tier",
)
VIEW_SPEC = (
    ("전체 메일 연결", None, None),
    ("프로젝트별 메일", "Project Link", "PROJECT_ID_EXACT"),
    ("고객 이메일 확인", "Contact Link", "EMAIL_EXACT_CONTACT"),
    ("연결 검토 필요", "Review State", "REVIEW"),
    ("현재 메일 연결", "Feed Lane", "CURRENT_30D"),
    ("과거 메일 연결", "Feed Lane", "HISTORY_2026"),
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
H_RE = re.compile(r"\bH\d{2,}SC\d+\b", re.I)
PROJECT_RE = re.compile(r"\bAMEA\d{7,}(?:-\d+)?\b", re.I)


def normalize_account(s):
    text = re.sub(r"[\s.\-()]+", "", str(s or "")).casefold()
    return {"고려대학": "고려대학교"}.get(text, text)


def official_contact_name(row):
    first = str(row.get("First Name") or "").strip()
    last = str(row.get("Last Name") or "").strip()
    # Do not assume first/last split direction; preserve exact source tokens.
    return " ".join(t for t in (first, last) if t)


def read_legacy_leads(session):
    """SFDC Import Leads has a duplicated Opportunity ID header in the source.
    Only allow that known duplicate; use its first occurrence. No Sheet writes.
    """
    location = urllib.parse.quote("'SFDC Import Leads'!A1:W700", safe="")
    url = ("https://sheets.googleapis.com/v4/spreadsheets/" + UNIFIED_SHEET +
           "/values/" + location)
    response = session.get(url, timeout=45)
    if not response.ok:
        raise SafeError("LEAD_REFERENCE_READ_HTTP_" + str(response.status_code))
    values = response.json().get("values") or []
    if not values:
        raise SafeError("LEAD_REFERENCE_EMPTY")
    headers = [str(v).strip() for v in values[0]]
    required = {"Email", "Contact Name", "Contact ID", "Account ID",
                "Company / Account", "Opportunity: Account"}
    if not required.issubset(set(headers)):
        raise SafeError("LEAD_REFERENCE_SCHEMA_MISMATCH")
    duplicates = {h for h in headers if headers.count(h) > 1}
    if duplicates - {"Opportunity ID"}:
        raise SafeError("LEAD_REFERENCE_UNEXPECTED_DUPLICATE_HEADERS")
    lookup = {name: headers.index(name) for name in required}
    return [{name: str(row[idx]).strip() if idx < len(row) else ""
             for name, idx in lookup.items()}
            for row in values[1:] if any(str(cell).strip() for cell in row)]


def load_references():
    session = sheets_session()
    source = {
        "contacts": req_sheet(session, UNIFIED_SHEET, "SFDC Contacts", 400),
        "leads": read_legacy_leads(session),
        "quotes": req_sheet(session, UNIFIED_SHEET, "SFDC Quote Export", 1200),
        "projects": req_sheet(session, CSS_SHEET, "CSS Project Dashboard", 700),
    }
    if not source["contacts"] or not source["projects"]:
        raise SafeError("IDENTITY_REFERENCE_TABLE_EMPTY")
    return source


def build_index(source):
    contact_email = collections.defaultdict(list)
    lead_email = collections.defaultdict(list)
    quote_project = collections.defaultdict(list)
    project_ids = collections.defaultdict(list)
    h_ids = collections.defaultdict(list)
    for row in source["contacts"]:
        address = str(row.get("Email") or "").strip().lower()
        if EMAIL_RE.fullmatch(address):
            contact_email[address].append({
                "name": official_contact_name(row), "account": str(row.get("Account Name") or "").strip(),
                "id": "", "account_id": "", "source": "SFDC_CONTACT_REFERENCE",
            })
    for row in source["leads"]:
        address = str(row.get("Email") or "").strip().lower()
        if not EMAIL_RE.fullmatch(address):
            continue
        lead_email[address].append({
            "name": str(row.get("Contact Name") or "").strip(),
            "account": str(row.get("Opportunity: Account") or row.get("Company / Account") or "").strip(),
            "id": str(row.get("Contact ID") or "").strip(),
            "account_id": str(row.get("Account ID") or "").strip(),
        })
    for row in source["quotes"]:
        project_id = str(row.get("AMEA Quotation ID") or "").strip().upper()
        if PROJECT_RE.fullmatch(project_id):
            quote_project[project_id].append(row)
    for row in source["projects"]:
        pid = str(row.get("project_id") or "").strip().upper()
        if not PROJECT_RE.fullmatch(pid):
            continue
        project_ids[pid].append(row)
        for h in set(H_RE.findall(str(row.get("h_project_numbers") or "").upper())):
            h_ids[h].append(row)
    return {
        "contacts": contact_email, "leads": lead_email,
        "quotes": quote_project, "projects": project_ids, "h_ids": h_ids,
    }


def unique_contact(rows):
    # Duplicate listings of exactly the same identity are okay, conflicting
    # account/name combinations for one email are not.
    dedup = {(normalize_account(x["account"]), x["name"].strip()): x for x in rows}
    if len(dedup) == 1:
        return next(iter(dedup.values())), False
    return None, len(dedup) > 1


def mail_contact(mail, index):
    direction = plain_field(mail.get("Direction")).strip()
    sender = email_set(plain_field(mail.get("From")))
    recipients = email_set(plain_field(mail.get("To"))) | email_set(plain_field(mail.get("CC")))
    # Inbound CSS automation is linked to a Project ID, never to the CSS sender.
    # Outbound uses To/CC only; multiple distinct contacts need review.
    lookup = (sender - {CSS}) if direction == "INBOUND" else recipients if direction == "OUTBOUND" else set()
    found = []
    leads = []
    ambiguous_email = False
    for addr in lookup:
        contact, ambiguous = unique_contact(index["contacts"].get(addr, []))
        ambiguous_email |= ambiguous
        if contact:
            found.append((addr, contact))
        if index["leads"].get(addr):
            leads.append(addr)
    distinct = {(normalize_account(x["account"]), x["name"]): x for _, x in found}
    if ambiguous_email or len(distinct) > 1:
        return None, "MULTIPLE_CONTACT_CANDIDATES", "REVIEW"
    if len(distinct) == 1:
        return next(iter(distinct.values())), "EMAIL_EXACT_CONTACT", "OK"
    if leads:
        return None, "LEAD_EMAIL_CANDIDATE", "REVIEW"
    return None, "NOT_MATCHED", "UNMATCHED"


def mail_project(mail, index):
    subject = plain_field(mail.get("Subject"))
    # Subject is stronger than quoted body: body references are NOT automatic.
    names = set(PROJECT_RE.findall(subject.upper()))
    names.update(PROJECT_RE.findall(plain_field(mail.get("AMEA")).upper()))
    h = set(H_RE.findall(subject.upper()))
    h.update(H_RE.findall(plain_field(mail.get("H Project")).upper()))
    matches = {}
    for x in names:
        for row in index["projects"].get(x, []):
            matches[str(row.get("project_id") or "").strip().upper()] = row
    for x in h:
        for row in index["h_ids"].get(x, []):
            matches[str(row.get("project_id") or "").strip().upper()] = row
    missing_tokens = any(x not in index["projects"] for x in names) or any(x not in index["h_ids"] for x in h)
    if len(matches) > 1:
        return None, "MULTIPLE_PROJECTS_REVIEW", "REVIEW"
    if len(matches) == 1:
        # Conflicting exact identifiers are not automatically accepted.
        if missing_tokens:
            return None, "PROJECT_ID_CONFLICT_REVIEW", "REVIEW"
        return next(iter(matches.values())), "PROJECT_ID_EXACT", "OK"
    if names or h:
        return None, "PROJECT_ID_UNMATCHED", "REVIEW"
    return None, "NO_PROJECT_ID", "UNMATCHED"


def company_address(address):
    return any(addr.rsplit("@", 1)[-1] in
               {"novogene.com", "novogene-amea.com", "novogene.cn"}
               for addr in email_set(address))


def mail_learning_route(mail, classification):
    """Routing for the *candidate pool*, not an unanswered-mail conclusion."""
    sender = email_set(plain_field(mail.get("From")))
    recipients = email_set(plain_field(mail.get("To"))) | email_set(plain_field(mail.get("CC")))
    direction = plain_field(mail.get("Direction")).strip()
    category = classification["Primary Category"]
    if direction == "OUTBOUND":
        return "OUTBOUND", "NOT_APPLICABLE"
    if direction != "INBOUND":
        return "DATE_OR_DIRECTION_REVIEW", "EXCLUDE_UNVERIFIED"
    if CSS in sender:
        return "CSS_AUTOMATED_NOTICE", "EXCLUDE_CSS"
    if category == "SYSTEM_REPORT":
        return "SYSTEM_REPORT", "EXCLUDE_SYSTEM"
    if sender and all(a.rsplit("@", 1)[-1] in
                      {"novogene.com", "novogene-amea.com", "novogene.cn"}
                      for a in sender):
        return "INTERNAL_MAIL", "EXCLUDE_INTERNAL"
    if sender:
        # Sent mail coverage and exact reply-chain correlation are not complete.
        return "EXTERNAL_INBOUND_CANDIDATE", "THREAD_REVIEW_REQUIRED"
    return "SENDER_MISSING", "EXCLUDE_UNVERIFIED"


def evidence_tier(category, contact_link, project_link, state):
    if state == "REVIEW":
        return "CONFLICT_REVIEW"
    if contact_link == "EMAIL_EXACT_CONTACT" and project_link == "PROJECT_ID_EXACT":
        return "EXACT_CONTACT_AND_PROJECT"
    if project_link == "PROJECT_ID_EXACT":
        return "EXACT_PROJECT_ONLY"
    if contact_link == "EMAIL_EXACT_CONTACT":
        return "EXACT_CONTACT_ONLY"
    return "NO_IDENTITY_PROOF"


def decorate(mail, index, now):
    # Feishu Bitable text fields may arrive as strings OR rich-text chunks.
    mail = {key: plain_field(value) for key, value in mail.items()}
    key = plain_field(mail.get("Mail Key")).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise SafeError("MAIL_IDENTITY_KEY_INVALID")
    if not since_2026(mail.get("Received At")):
        return None
    contact, contact_link, contact_review = mail_contact(mail, index)
    project, project_link, project_review = mail_project(mail, index)
    subject = plain_field(mail.get("Subject"))
    classification = classify(mail)
    mail_role, followup_pool = mail_learning_route(mail, classification)
    account = contact["account"] if contact else ""
    account_id = contact["account_id"] if contact else ""
    contact_name = contact["name"] if contact else ""
    contact_id = contact["id"] if contact else ""
    project_id = str(project.get("project_id") or "").strip().upper() if project else ""
    opportunity_id = ""
    h_project = str(project.get("h_project_numbers") or "").strip() if project else ""
    evidence = []
    if contact:
        evidence.append("SFDC_CONTACT_EMAIL_EXACT_REFERENCE")
        # Only enrich IDs if the converted lead contains this exact email and
        # consistent account; never accept an unmatched/ambiguous contact ID.
        lookup = email_set(plain_field(mail.get("From"))) if mail.get("Direction") == "INBOUND" else (
            email_set(plain_field(mail.get("To"))) | email_set(plain_field(mail.get("CC"))))
        ids = {(r["id"],r["account_id"]) for addr in lookup for r in index["leads"].get(addr,[])
               if r["id"] and normalize_account(r["account"]) == normalize_account(account)}
        if len(ids) == 1:
            contact_id, account_id = next(iter(ids))
            evidence.append("CONVERTED_LEAD_CONTACT_ID_REFERENCE")
        elif len(ids) > 1:
            contact_review = "REVIEW"
            evidence.append("CONFLICTING_CONVERTED_LEAD_IDS")
    if project:
        evidence.append("CSS_PROJECT_ID_EXACT_REFERENCE")
        project_account = str(project.get("institution") or "").strip()
        project_customer = str(project.get("customer_name") or "").strip()
        if contact and account and project_account and normalize_account(account) != normalize_account(project_account):
            project_review = "REVIEW"
            evidence.append("CONTACT_PROJECT_ACCOUNT_CONFLICT")
        if not contact:
            account = project_account
            contact_name = project_customer
            evidence.append("PROJECT_CUSTOMER_NAME_ONLY_NOT_CONTACT_VERIFIED")
        qs = index["quotes"].get(project_id, [])
        opps = {str(q.get("Opportunity ID") or "").strip() for q in qs
                if str(q.get("Opportunity ID") or "").strip()}
        if len(opps) == 1:
            # Project->Quote->Opportunity is a reference link, not an identity proof.
            opportunity_id = next(iter(opps))
            evidence.append("SINGLE_SFDC_QUOTE_OPPORTUNITY_REFERENCE")
        elif len(opps) > 1:
            evidence.append("MULTIPLE_QUOTE_OPPORTUNITY_CANDIDATES")
            project_review = "REVIEW"
    if contact_review == "REVIEW" or project_review == "REVIEW":
        state = "REVIEW"
    elif contact or project:
        state = "LINKED"
    else:
        state = "UNMATCHED"
    if mail.get("Direction") == "INBOUND" and CSS in email_set(plain_field(mail.get("From"))) and not project:
        state = "REVIEW"
        evidence.append("CSS_WITHOUT_EXACT_PROJECT")
    lane = segment(mail.get("Received At"), now, 30)
    received = parse_aware(mail.get("Received At"))
    return {
        "Mail Key": key, "Received KST": received.strftime("%Y-%m-%d %H:%M") if received else "",
        "Feed Lane": lane, "Direction": plain_field(mail.get("Direction")),
        "Subject": subject[:500], "Primary Category": classification["Primary Category"],
        "Milestone": classification["Milestone"],
        "Account": account, "Account ID": account_id,
        "Contact": contact_name, "Contact ID": contact_id,
        "Project ID": project_id, "H Project": h_project,
        "Opportunity ID": opportunity_id,
        "Contact Link": contact_link, "Project Link": project_link,
        "Relationship Status": state, "Review State": "REVIEW" if state == "REVIEW" else "OK",
        "Evidence": ", ".join(evidence) if evidence else "NO_IDENTITY_REFERENCE",
        "Owner Evidence": "NOT_VERIFIED",
        "Reference Basis": "Legacy SFDC/CSS lists read-only; original mail Feishu direct",
        "Classification Tags": classification["Tags"],
        "Rule Version": classification["Rule Version"],
        "Classification Evidence": classification["Evidence"],
        "Mail Role": mail_role,
        "Followup Pool": followup_pool,
        "Evidence Tier": evidence_tier(classification["Primary Category"],
                                      contact_link, project_link, state),
    }


def field_text(value):
    return plain_field(value).strip()


def same(old, expected):
    return all(field_text(old.get(key)) == str(val).strip() for key, val in expected.items()
               if key != "Last Sync KST")


def get_or_create_table(token, root):
    tables = list_all(root + "/tables", token, "identity_list_tables")
    matches = [r for r in tables if r.get("name") == TABLE]
    if len(matches) > 1:
        raise SafeError("IDENTITY_DUPLICATE_TABLE")
    if not matches:
        api("POST", root + "/tables", token, data={"table": {
            "name": TABLE, "default_view_name": "All",
            "fields": [{"field_name": k, "type": 1} for k in SCHEMA],
        }}, action="identity_create_table")
        matches = [r for r in list_all(root + "/tables", token, "identity_table_readback")
                   if r.get("name") == TABLE]
    if len(matches) != 1:
        raise SafeError("IDENTITY_CREATE_READBACK_FAILED")
    tid = matches[0].get("table_id")
    path = root + "/tables/" + urllib.parse.quote(tid, safe="")
    fields = {r.get("field_name"): r.get("type") for r in list_all(path + "/fields", token, "identity_schema")}
    if any(k in fields and fields[k] != 1 for k in SCHEMA):
        raise SafeError("IDENTITY_SCHEMA_CONFLICT")
    for name in SCHEMA:
        if name not in fields:
            api("POST", path + "/fields", token,
                data={"field_name": name, "type": 1},
                action="identity_add_derived_field")
            print("IDENTITY_DERIVED_FIELD_CREATED=" + name)
    fields = {r.get("field_name"): r.get("type") for r in list_all(path + "/fields", token, "identity_schema_recheck")}
    if any(fields.get(k) != 1 for k in SCHEMA):
        raise SafeError("IDENTITY_SCHEMA_MISMATCH")
    return tid, path


def ensure_views(token, tid, path):
    field_ids = field_map(token, path)
    for title, field, value in VIEW_SPEC:
        vid, _ = resolve_view(token, path, title, field is not None)
        view = get_view(token, path, vid)
        if field:
            fid = field_ids.get(field)
            if not fid:
                raise SafeError("IDENTITY_VIEW_FIELD_MISSING")
            if not (view.get("view_name") == title and filter_matches(view, fid, value)):
                import json
                api("PATCH", path + "/views/" + urllib.parse.quote(vid, safe=""),
                    token, data={"view_name": title, "property": {"filter_info": {
                        "conjunction": "and", "conditions": [{"field_id": fid,
                            "operator": "is", "value": json.dumps([value])}]
                    }}}, action="identity_filter_view")
                view = get_view(token, path, vid)
                if not (view.get("view_name") == title and filter_matches(view, fid, value)):
                    raise SafeError("IDENTITY_FILTER_READBACK_FAILED")
        elif view.get("view_name") != title:
            raise SafeError("IDENTITY_VIEW_READBACK_FAILED")
        print("IDENTITY_VIEW_READY=" + title + " URL=" + BASE_URL + "?table=" + tid + "&view=" + vid)


def changes(token, path, records, limit):
    existing = list_all(path + "/records", token, "identity_list_records")
    bykey = {}
    for x in existing:
        key = field_text((x.get("fields") or {}).get("Mail Key"))
        if not key:
            continue
        if key in bykey:
            raise SafeError("IDENTITY_DUPLICATE_MAIL_KEY")
        bykey[key] = x
    creates, updates, unchanged = [], [], 0
    for row in records:
        key = row["Mail Key"]
        old = bykey.get(key)
        if old and same(old.get("fields") or {}, row):
            unchanged += 1
            continue
        if len(creates) + len(updates) >= limit:
            continue
        now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
        fields = {**row, "Last Sync KST": now}
        if old:
            updates.append({"record_id": old["record_id"], "fields": fields})
        else:
            creates.append({"fields": fields})
    return creates, updates, unchanged


def batch_apply(token, path, creates, updates):
    for action, url, rows in (
        ("identity_batch_create", path + "/records/batch_create", creates),
        ("identity_batch_update", path + "/records/batch_update", updates),
    ):
        for offset in range(0, len(rows), 25):
            batch = rows[offset:offset + 25]
            data = api("POST", url, token, data={"records": batch}, action=action)
            returned = data.get("records") or []
            if len(returned) != len(batch) or any(not r.get("record_id") for r in returned):
                raise SafeError(action + "_UNCONFIRMED")
            # Do not amplify Feishu rate limits on larger 2026 archives.
            if len(rows) > 500:
                import time
                time.sleep(0.20)
    # Independently verify by stable Mail Key, not by record-order response.
    if creates or updates:
        checked = list_all(path + "/records", token, "identity_readback")
        keys = {}
        for r in checked:
            k = field_text((r.get("fields") or {}).get("Mail Key"))
            if not k:
                continue
            if k in keys:
                raise SafeError("IDENTITY_DUPLICATE_AFTER_APPLY")
            keys[k] = r.get("fields") or {}
        for entry in creates + updates:
            item = entry["fields"]
            if not same(keys.get(item["Mail Key"], {}), item):
                raise SafeError("IDENTITY_READBACK_MISMATCH")


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("IDENTITY_REFUSE_OTHER_FEISHU_BASE")
    mode = os.environ.get("FEISHU_IDENTITY_MODE", "plan")
    if mode not in ("plan", "apply"):
        raise SafeError("IDENTITY_UNKNOWN_MODE")
    limit = min(15000, max(1, int(os.environ.get("FEISHU_IDENTITY_BATCH_LIMIT", "7500"))))
    token, root = auth()
    table_id = find_table(token, root)
    if not table_id:
        raise SafeError("IDENTITY_SOURCE_QQ_INTAKE_MISSING")
    raw_path = root + "/tables/" + urllib.parse.quote(table_id, safe="")
    raw = list_all(raw_path + "/records", token, "identity_read_raw")
    refs = load_references()
    idx = build_index(refs)
    now = dt.datetime.now(KST)
    desired = []
    for item in raw:
        fields = item.get("fields") or {}
        if field_text(fields.get("Mail Key")) == SMOKE_KEY:
            continue
        mapped = decorate(fields, idx, now)
        if mapped:
            desired.append(mapped)
    keys = [r["Mail Key"] for r in desired]
    if len(keys) != len(set(keys)):
        raise SafeError("IDENTITY_DUPLICATE_SOURCE_MAIL")
    stats = collections.Counter(r["Relationship Status"] for r in desired)
    contacts = sum(r["Contact Link"] == "EMAIL_EXACT_CONTACT" for r in desired)
    projects = sum(r["Project Link"] == "PROJECT_ID_EXACT" for r in desired)
    histories = sum(r["Feed Lane"] == "HISTORY_2026" for r in desired)
    category_counts = collections.Counter(r["Primary Category"] for r in desired)
    role_counts = collections.Counter(r["Mail Role"] for r in desired)
    followup_counts = collections.Counter(r["Followup Pool"] for r in desired)
    for category, count in sorted(category_counts.items()):
        print("MAIL_LEARNING_CATEGORY_" + category + "=" + str(count))
    for role, count in sorted(role_counts.items()):
        print("MAIL_LEARNING_ROLE_" + role + "=" + str(count))
    for role, count in sorted(followup_counts.items()):
        print("MAIL_LEARNING_FOLLOWUP_" + role + "=" + str(count))
    print("IDENTITY_SOURCE_2026=" + str(len(desired)) +
          " project_exact=" + str(projects) + " contact_email_exact=" + str(contacts) +
          " history=" + str(histories) +
          " linked=" + str(stats["LINKED"]) +
          " review=" + str(stats["REVIEW"]) +
          " unmatched=" + str(stats["UNMATCHED"]))
    print("IDENTITY_REFERENCE_LISTS contacts=" + str(len(refs["contacts"])) +
          " leads=" + str(len(refs["leads"])) +
          " quotes=" + str(len(refs["quotes"])) +
          " projects=" + str(len(refs["projects"])))
    if mode == "plan":
        print("IDENTITY_PLAN_PASS writes=0")
        return
    tid, path = get_or_create_table(token, root)
    ensure_views(token, tid, path)
    creates, updates, unchanged = changes(token, path, desired, limit)
    batch_apply(token, path, creates, updates)
    print("IDENTITY_APPLY_PASS created=" + str(len(creates)) +
          " updated=" + str(len(updates)) + " unchanged=" + str(unchanged) +
          " total=" + str(len(desired)) + " remaining=" +
          str(max(0, len(desired) - unchanged - len(creates) - len(updates))) +
          " sheets_writes=0 original_mail_writes=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("IDENTITY_SYNC_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
