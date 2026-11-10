#!/usr/bin/env python3
"""QQ customer reply-review queue, built from canonical *staging* mail headers.

Advisory evidence only. Never sends email, modifies mail, or overwrites the
legacy Unanswered Emails / exclusions / reviewer ledgers.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from collections import Counter, defaultdict

import incremental_sync as src
import canonical_mail_reader as canonical
from unanswered_auto import addresses, norm_subject, truth, when, table
import unanswered_review_decisions as decisions

TAB = "Unanswered Reply Review 60D"
AUDIT = "Unanswered Reply Audit"
HEAD = [
    "Priority", "Waiting Days", "Last Customer Mail (KST)", "Customer Email",
    "Subject / Thread", "Project IDs", "Reply Evidence", "Suggested Action",
    "Assessment", "Thread Identity", "Mail UID", "Last Possible Outbound (KST)",
    "To", "Cc", "Canonical Ingest Key", "Source Fetched (UTC)",
    "Checked (UTC)", "Source Coverage", "Manual Decision Source",
]
AUDIT_HEAD = ["Metric", "Value", "Explanation"]
CAP = 1500
UTC = dt.timezone.utc
DELEGATES = frozenset(("masiyuan8900@novogene.com", "jiin.yoo@novogene.com"))
SYSTEM_SENDERS = frozenset(("css@novogene-amea.com",))
ID_PATTERN = re.compile(r"<[^<>\s]+>")
SHEET_URL = "https://docs.google.com/spreadsheets/d/" + src.BOOK + "/edit"


def ids(value):
    """Parse Message-ID / In-Reply-To / References without substring matches."""
    s = str(value or "").strip().casefold()
    items = set(ID_PATTERN.findall(s))
    if not items and s and "@" in s and not any(c.isspace() for c in s):
        items = {"<" + s.strip("<>") + ">"}
    return items


def ordered_refs(value):
    return ID_PATTERN.findall(str(value or "").strip().casefold())


def internal(addr):
    return addr.endswith("@novogene.com") or addr.endswith("@novogene-amea.com")


def exclusions_from_tables(mail_exclusions, sender_exclusions, sender_rules):
    banned_ids = set()
    thread_blocks = []
    sender_patterns = []
    for row in mail_exclusions:
        if truth(row.get("restore")):
            continue
        uid = str(row.get("uid", "")).strip().casefold()
        if uid:
            banned_ids.add(uid)
        cutoff = when(row.get("excluded_through_at")) or when(row.get("excluded_at"))
        sender = addresses(row.get("from_email"))
        subject = norm_subject(row.get("thread_subject") or row.get("subject"))
        if cutoff and sender and subject:
            thread_blocks.append((sender, subject, cutoff))
    for row in sender_exclusions:
        if truth(row.get("restore")):
            continue
        pat = str(row.get("sender_pattern", "")).strip().casefold()
        kind = str(row.get("match_type", "")).strip().casefold()
        if pat and kind in ("exact", "domain", "contains"):
            sender_patterns.append((pat, kind))
    for row in sender_rules:
        if not truth(row.get("active")):
            continue
        if str(row.get("default_action", "")).strip().upper() not in (
            "IGNORE", "ARCHIVE", "SALESFORCE_PIPELINE"
        ):
            continue
        pat = str(row.get("sender_pattern", "")).strip().casefold()
        kind = str(row.get("match_type", "")).strip().casefold()
        if pat and kind in ("exact", "prefix", "contains"):
            sender_patterns.append((pat, kind))
    return banned_ids, thread_blocks, sender_patterns


def is_ignored(address_set, patterns):
    for email in address_set:
        for pat, kind in patterns:
            if kind == "exact" and email == pat:
                return True
            if kind == "domain" and email.endswith("@" + pat.lstrip("@")):
                return True
            if kind == "contains" and pat in email:
                return True
            if kind == "prefix" and email.split("@")[0].startswith(pat):
                return True
    return False


def parse(messages):
    parsed = []
    seen = set()
    for row in messages:
        if row.get("direction") not in ("INBOUND", "OUTBOUND"):
            continue
        key = str(row.get("ingest_key", "")).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        at = when(row.get("received_at"))
        if at is None:
            continue
        item = dict(row)
        item["_at"] = at
        item["_sender"] = addresses(row.get("from_email"))
        item["_to"] = addresses(row.get("recipient_to")) | addresses(row.get("cc"))
        item["_subject"] = norm_subject(row.get("subject"))
        item["_id"] = next(iter(ids(row.get("message_id"))), "")
        item["_references"] = ids(row.get("references")) | ids(row.get("in_reply_to"))
        refs_ordered = ordered_refs(row.get("references")) or ordered_refs(row.get("in_reply_to"))
        item["_root"] = refs_ordered[0] if refs_ordered else item["_id"] or key.casefold()
        parsed.append(item)
    return parsed


def analyze(messages, mail_exclusions=(), sender_exclusions=(), sender_rules=(),
            *, own_address, now=None, lookback_days=60, min_days=2, max_days=30):
    """Return candidate rows and sanitized evidence counts. Never claim no reply."""
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware now required")
    now = now.astimezone(UTC)
    owners = addresses(own_address)
    if not owners:
        raise ValueError("CSS_QQ_MAIL_ADDRESS_REQUIRED")
    lookback = max(1, min(60, int(lookback_days)))
    min_days = max(1, min(60, int(min_days)))
    max_days = max(min_days, min(60, int(max_days)))
    banned_ids, blocked_threads, patterns = exclusions_from_tables(
        mail_exclusions, sender_exclusions, sender_rules
    )
    parsed = parse(messages)
    inbound = []
    outbound = []
    for row in parsed:
        if row["direction"] == "OUTBOUND":
            outbound.append(row)
        elif row["_sender"] & DELEGATES and any(
            not internal(addr) for addr in row["_to"]
        ):
            outbound.append(row)  # An internal teammate copied our mailbox.
        else:
            inbound.append(row)
    sent_by_id = defaultdict(list)
    sent_by_subject = defaultdict(list)
    for sent in outbound:
        external = {a for a in sent["_to"] if not internal(a)}
        for recipient in external:
            if sent["_subject"]:
                sent_by_subject[(recipient, sent["_subject"])].append(sent)
            for referenced_id in sent["_references"]:
                sent_by_id[(recipient, referenced_id)].append(sent)

    conversations = {}
    scanned = 0
    excluded = 0
    for row in inbound:
        sender_set = row["_sender"]
        if not sender_set or not row["_subject"]:
            continue
        if sender_set & SYSTEM_SENDERS or all(internal(x) for x in sender_set):
            continue
        if not row["_to"] & owners:
            continue
        if not dt.timedelta(0) <= now - row["_at"] <= dt.timedelta(days=lookback):
            continue
        scanned += 1
        # The original UID exclusion contract includes inbox:<imap_uid>.
        uid = str(row.get("imap_uid", "")).strip()
        key = str(row.get("ingest_key", "")).casefold()
        if key in banned_ids or uid.casefold() in banned_ids or (
            "inbox:" + uid.casefold() in banned_ids
        ):
            excluded += 1
            continue
        if is_ignored(sender_set, patterns):
            excluded += 1
            continue
        if any(
            sender_set & blocked_sender and row["_subject"] == subject
            and row["_at"] <= cutoff
            for blocked_sender, subject, cutoff in blocked_threads
        ):
            excluded += 1
            continue
        # Root Message-ID identifies independent, same-subject conversations.
        # Fallback to the ingest key rather than merging unrelated threads.
        identity = (tuple(sorted(sender_set)), row["_subject"], row["_root"])
        current = conversations.get(identity)
        if current is None or row["_at"] > current["_at"]:
            conversations[identity] = row

    results = []
    counts = Counter()
    last_fetch = max(
        (when(row.get("fetched_at_utc")) for row in parsed
         if when(row.get("fetched_at_utc")) is not None),
        default=None,
    )
    for row in conversations.values():
        sender_set = row["_sender"]
        sent_later = []
        for addr in sender_set:
            sent_later.extend(
                s for s in sent_by_subject.get((addr, row["_subject"]), [])
                if s["_at"] >= row["_at"]
            )
        dedup = {s["ingest_key"]: s for s in sent_later}
        sent_later = list(dedup.values())
        # Message-ID must explicitly reference the *latest* incoming email.
        # References to an older mail cannot close a renewed customer question.
        exact = []
        if row["_id"]:
            for addr in sender_set:
                exact.extend(
                    s for s in sent_by_id.get((addr, row["_id"]), [])
                    if s["_at"] >= row["_at"]
                )
        if exact:
            counts["EXACT_REPLY_EVIDENCE"] += 1
            continue
        days = max(0, (now.astimezone(src.KST).date()
                       - row["_at"].astimezone(src.KST).date()).days)
        if sent_later:
            evidence = "POSSIBLE_SUBJECT_MATCH"
            action = "보낸메일 대화 연결 확인"
            counts[evidence] += 1
        else:
            evidence = "NO_REPLY_EVIDENCE"
            action = "회신 필요 여부 검토"
            counts[evidence] += 1
        priority = ("WATCH" if days < min_days else
                    "P0" if days >= 6 and days <= max_days else
                    "P1" if days >= 3 and days <= max_days else
                    "P2" if days <= max_days else "OLD_REVIEW")
        if priority == "WATCH":
            action = "관찰 중 · 경과일 미달"
        if priority == "OLD_REVIEW":
            action = "장기 미회신 · 조치 필요성 재검토"
        ids_text = " | ".join(filter(None, [
            str(row.get(field, "")) for field in
            ("amea_numbers", "h_project_numbers", "sam_numbers", "batch_numbers")
        ]))
        newest_sent = max((r["_at"] for r in sent_later), default=None)
        results.append([
            priority, days, row["_at"].astimezone(src.KST).strftime("%Y-%m-%d %H:%M"),
            ", ".join(sorted(sender_set)), str(row.get("subject", ""))[:500],
            ids_text, evidence, action, "CANDIDATE_NOT_CONFIRMED",
            row["_root"], "inbox:" + str(row.get("imap_uid", "")),
            newest_sent.astimezone(src.KST).strftime("%Y-%m-%d %H:%M") if newest_sent else "",
            row.get("recipient_to", ""), row.get("cc", ""),
            row.get("ingest_key", ""), row.get("fetched_at_utc", ""),
            now.isoformat(), "STAGING_METADATA_PARTIAL_HISTORY",
            "BI Mail Review & Exclusions (manual)",
        ])
    weight = {"P0":0,"P1":1,"P2":2,"WATCH":3,"OLD_REVIEW":4}
    results.sort(key=lambda r: (weight[r[0]], -int(r[1]), r[2], r[10]))
    counts["SCAN_CUSTOMER_MESSAGES"] = scanned
    counts["EXCLUDED_MESSAGES"] = excluded
    counts["INBOUND_METADATA"] = len(inbound)
    counts["OUTBOUND_METADATA"] = len(outbound)
    counts["THREADS_REVIEWED"] = len(conversations)
    counts["ROWS_WRITTEN"] = min(len(results), CAP)
    counts["TRUNCATED"] = max(0, len(results) - CAP)
    counts["SOURCE_LAST_FETCH_UTC"] = last_fetch.isoformat() if last_fetch else ""
    counts["SOURCE_LAST_FETCH_AGE_HOURS"] = (
        round((now-last_fetch).total_seconds()/3600, 1) if last_fetch else ""
    )
    return results[:CAP], counts


def url_for(tab, region):
    return src.endpoint("/values/" + urllib.parse.quote("'" + tab + "'!" + region, safe=""))


def sheet_titles(session):
    meta = src.api(session, "GET", src.endpoint() + "?fields=sheets.properties(sheetId,title,gridProperties)")
    return {v["properties"]["title"]:v["properties"] for v in meta.get("sheets", [])}


def read_rows(session, name, end="X2000"):
    return src.api(session, "GET", url_for(name, "A1:" + end)).get("values", [])


def ensure_ledger(session, name, header):
    found = sheet_titles(session)
    if name not in found:
        src.api(session, "POST", src.endpoint(":batchUpdate"), json={"requests":[
            {"addSheet":{"properties":{"title":name,"gridProperties":{
                "rowCount":2000,"columnCount":max(12,len(header)),
                "frozenRowCount":1
            }}}}
        ]})
    rows = read_rows(session, name, "H2000")
    if not rows:
        src.api(session, "PUT", url_for(name, "A1") + "?valueInputOption=RAW",
                json={"values":[header]})
        return [header]
    if list(rows[0]) != header:
        raise RuntimeError("MANUAL_LEDGER_SCHEMA_CHANGED_" + name)
    return rows


def append_ledger(session, name, header, entries):
    if not entries:
        return
    latest = read_rows(session, name, "H2000")
    if not latest or list(latest[0]) != header:
        raise RuntimeError("MANUAL_LEDGER_CHANGED_" + name)
    # Fail closed if another run has already appended the same identity.
    key_idx = 2
    keys = {(str(r[1]).strip().upper(), str(r[key_idx]).strip().casefold())
            for r in latest[1:] if len(r)>key_idx}
    for item in entries:
        k = (str(item[1]).strip().upper(), str(item[2]).strip().casefold())
        if k in keys:
            raise RuntimeError("CONCURRENT_REVIEW_LEDGER_APPEND")
        keys.add(k)
    src.api(session, "POST", url_for(name, "A1:H2000") +
            ":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            json={"values":entries})
    verify = read_rows(session, name, "H2000")
    after = {(str(r[1]).strip().upper(), str(r[2]).strip().casefold())
             for r in verify[1:] if len(r)>2}
    if any((str(item[1]).strip().upper(), str(item[2]).strip().casefold())
           not in after for item in entries):
        raise RuntimeError("REVIEW_LEDGER_APPEND_READBACK_FAILED")


def publish_review(session, records):
    current = sheet_titles(session)
    head = HEAD + decisions.APPEND_HEAD
    if TAB not in current:
        raise RuntimeError("GENERATED_REVIEW_TAB_MISSING")
    props = current[TAB]
    if props["gridProperties"]["rowCount"] < len(records)+1:
        raise RuntimeError("REVIEW_QUEUE_TOO_MANY_ROWS")
    if props["gridProperties"].get("columnCount",0) < len(head):
        src.api(session,"POST",src.endpoint(":batchUpdate"),json={"requests":[
            {"updateSheetProperties":{"properties":{
                "sheetId":props["sheetId"],"gridProperties":{"columnCount":len(head)}
            },"fields":"gridProperties.columnCount"}}
        ]})
    before = read_rows(session, TAB)
    if before and list(before[0]) not in (HEAD, head):
        raise RuntimeError("REVIEW_QUEUE_HEADER_CHANGED")
    # Decisions were already durably committed. All input rows are consumed.
    # Future updates rebuild the 60-day list; manual history stays in ledgers.
    data = [head] + records
    src.api(session,"PUT",url_for(TAB,"A1")+"?valueInputOption=RAW",
            json={"values":data})
    readback = read_rows(session, TAB, "X" + str(len(data)))
    if len(readback)!=len(data) or readback[0]!=head or any(
        str(r[14]) != str(data[i][14]) for i,r in enumerate(readback[1:],start=1)
    ):
        raise RuntimeError("REVIEW_QUEUE_READBACK_MISMATCH")
    if len(data)<2000:
        src.api(session,"POST",url_for(TAB,"A"+str(len(data)+1)+":X2000")+
                ":clear",json={})
    # Only U is editable action selection. T is read-only receipt role.
    src.api(session,"POST",src.endpoint(":batchUpdate"),json={"requests":[
        {"setDataValidation":{"range":{"sheetId":props["sheetId"],
           "startRowIndex":1,"endRowIndex":2000,
           "startColumnIndex":20,"endColumnIndex":21},
         "rule":{"condition":{"type":"ONE_OF_LIST","values":[
            {"userEnteredValue":"SKIP_MAIL"},
            {"userEnteredValue":"SKIP_CC_TO"},
            {"userEnteredValue":"SKIP_CC_SENDER"}]},
          "showCustomUi":True,"strict":True}}}
    ]})


def publish(session, title, header, records):
    titles = sheet_titles(session)
    if title not in titles:
        src.api(session, "POST", src.endpoint(":batchUpdate"), json={"requests":[
            {"addSheet":{"properties":{"title":title,"gridProperties":{
                "rowCount":max(2000,len(records)+10),"columnCount":max(21,len(header)),
                "frozenRowCount":1
            }}}}
        ]})
    else:
        old = src.api(session, "GET", url_for(title, "A1:Z1")).get("values", [])
        if old and old[0] != header:
            raise RuntimeError("REVIEW_OUTPUT_HEADER_CHANGED_" + title)
        props = titles[title].get("gridProperties", {})
        if props.get("rowCount",0) < len(records)+1:
            raise RuntimeError("REVIEW_OUTPUT_GRID_TOO_SMALL_" + title)
    data = [header] + records
    src.api(session, "PUT", url_for(title, "A1") + "?valueInputOption=RAW",
            json={"values":data})
    verify = src.api(session, "GET", url_for(title, "A1:A" + str(len(data)))).get("values", [])
    if not verify or verify[0] != [header[0]] or len(verify) != len(data):
        raise RuntimeError("REVIEW_OUTPUT_READBACK_FAILED_" + title)
    # Clear only the generated tail, after the new snapshot has been verified.
    if len(data) < 2000:
        src.api(session, "POST", url_for(title, "A" + str(len(data)+1) + ":S2000") +
                ":clear", json={})


def main():
    own = os.environ.get("CSS_QQ_MAIL_ADDRESS", "")
    if not addresses(own):
        raise RuntimeError("CSS_QQ_MAIL_ADDRESS_REQUIRED")
    session = src.authorize()
    canonical_rows = canonical.read_staging_compatible(session)
    if canonical_rows[0] != src.COLS:
        raise RuntimeError("CANONICAL_PROJECTION_SCHEMA_CHANGED")
    messages = [
        dict(zip(src.COLS, list(row) + [""] * (len(src.COLS)-len(row))))
        for row in canonical_rows[1:]
    ]
    # Fail closed before writing. Missing sent metadata is not evidence of no reply.
    if not messages or not any(r.get("direction") == "OUTBOUND" for r in messages):
        raise RuntimeError("SENT_OR_CANONICAL_SOURCE_UNAVAILABLE")
    mail = table(session, "Unanswered Email Exclusions", "L", 10000)
    sender = table(session, "Unanswered Sender Exclusions", "F", 10000)
    sender_rules = table(session, "CSS Sender Rules", "G", 200)
    rules = table(session, "CSS Rules & SLA", "I", 300)
    def rule(key, default):
        for r in rules:
            if (r.get("rule_key") == key and r.get("rule_group") == "Mail"
                    and truth(r.get("enabled"))):
                try:
                    return int(r.get("value"))
                except (ValueError,TypeError):
                    pass
        return default
    results, counts = analyze(
        messages, mail, sender, sender_rules, own_address=own,
        lookback_days=min(60,rule("unanswered_lookback_days",60)),
        min_days=rule("action_unanswered_min_age_days",2),
        max_days=rule("action_unanswered_max_age_days",30)
    )
    last_fetch = counts.get("SOURCE_LAST_FETCH_AGE_HOURS")
    if last_fetch == "" or last_fetch < -1 or last_fetch > 72:
        raise RuntimeError("CANONICAL_SOURCE_STALE_OR_UNVERIFIED")
    audit = [
        ["Snapshot UTC", dt.datetime.now(UTC).isoformat(), "Metadata only"],
        ["Source", "Canonical Mail Ledger / CSS Git Ingest", "Legacy mail not used for reply proof"],
        ["Coverage", "STAGING_METADATA_PARTIAL_HISTORY", "60-day scan window is not proven complete"],
        ["Lookback days", min(60,rule("unanswered_lookback_days",60)), "Hard maximum 60"],
    ]
    for key in ("INBOUND_METADATA","OUTBOUND_METADATA","SCAN_CUSTOMER_MESSAGES",
                "THREADS_REVIEWED","EXACT_REPLY_EVIDENCE","NO_REPLY_EVIDENCE",
                "POSSIBLE_SUBJECT_MATCH","EXCLUDED_MESSAGES","ROWS_WRITTEN",
                "TRUNCATED","SOURCE_LAST_FETCH_UTC","SOURCE_LAST_FETCH_AGE_HOURS"):
        audit.append([key, counts.get(key,0), "Counts from available canonical staging"])
    decision_rows = ensure_ledger(session, decisions.DECISIONS_TAB, decisions.DECISION_HEAD)
    routing_rows = ensure_ledger(session, decisions.RULES_TAB, decisions.RULE_HEAD)
    queue_rows = read_rows(session, TAB)
    if not queue_rows:
        queue_rows = [HEAD]
    new_mail, new_rules = decisions.plan(
        queue_rows, results, decision_rows, routing_rows, own
    )
    append_ledger(session, decisions.DECISIONS_TAB, decisions.DECISION_HEAD, new_mail)
    append_ledger(session, decisions.RULES_TAB, decisions.RULE_HEAD, new_rules)
    combined_mail = decision_rows + new_mail
    combined_rules = routing_rows + new_rules
    visible, review_stats = decisions.filtered_queue(
        results, combined_mail, combined_rules, own
    )
    if not results and queue_rows and len(queue_rows)>1:
        raise RuntimeError("EMPTY_SOURCE_REVIEW_WOULD_CLEAR_QUEUE")
    audit.extend([
        ["SKIP_MAIL_NEW",len(new_mail),"Explicit manual per-message action"],
        ["SKIP_CC_RULE_NEW",len(new_rules),"Exact address, CC-only"],
        ["VISIBLE_AFTER_REVIEW",len(visible),"Manual skips and active rules applied"],
    ])
    for k,v in sorted(review_stats.items()):
        audit.append([k,v,"Manual decisions and CC-only routing"])
    publish_review(session, visible)
    publish(session, AUDIT, AUDIT_HEAD, audit)
    print("CSS_UNANSWERED_REPLY_REVIEW_PASS " + json.dumps({
        "candidate_rows":len(results), "visible":len(visible), "new_skip":len(new_mail), "new_cc_rules":len(new_rules), "exact_replies":counts["EXACT_REPLY_EVIDENCE"],
        "possible_reply":counts["POSSIBLE_SUBJECT_MATCH"],
        "source_age_h":last_fetch, "truncated":counts["TRUNCATED"],
        "coverage":"STAGING_METADATA_PARTIAL_HISTORY"
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("CSS_UNANSWERED_REPLY_REVIEW_FAILED " + type(exc).__name__ +
              ":" + str(exc)[:100], file=sys.stderr)
        sys.exit(1)
