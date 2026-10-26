"""Read-only audit of QQ unanswered evidence quality for NBA.

Do not infer replies from customer names, matching subjects, or review notes.
Report confirmed replies separately from ambiguous triage evidence.
"""
from collections import Counter
from today_action_v2 import mail_rows

CONFIRMED = {
    "REPLIED", "ANSWERED", "REPLY_SENT",
    "PC_REPLIED", "TS_REPLIED", "DELEGATE_REPLIED",
}
CONFIRMED_ACTION = {"DONE", "COMPLETED", "CLOSED", "EXCLUDED", "SKIP"}


def summarize(rows):
    counts = Counter()
    for r in rows:
        if not str(r.get("Thread UID") or "").strip():
            continue
        counts["threads"] += 1
        try:
            age = int(float(r.get("Aging Days") or -1))
        except (TypeError, ValueError):
            age = -1
        reply = str(r.get("Reply Evidence") or "").strip().upper()
        reviewer = str(r.get("Reviewer Mail Action") or "").strip().upper()
        if reply in CONFIRMED:
            counts["explicit_reply_evidence"] += 1
        elif reviewer in CONFIRMED:
            counts["explicit_reply_evidence"] += 1
        elif reviewer in CONFIRMED_ACTION:
            counts["reviewer_closed_not_reply_proof"] += 1
        elif reply and reply not in {"NONE", "UNKNOWN"}:
            counts["nonproof_status_text"] += 1
        if age > 30:
            counts["historical_over_30d"] += 1
    counts["nba_actionable"] = len(mail_rows(rows))
    return dict(counts)



def exact_header_reply_links(rows):
    """Count strict sender/recipient reversed links; never auto-close a thread."""
    import re
    pattern = re.compile(r"<[^<>\s]+>")
    outgoing = {}
    for row in rows:
        folder = str(row.get("folder") or "").upper()
        sender = str(row.get("from_email") or "").strip().lower()
        recipient = str(row.get("recipient_to") or "").strip().lower()
        message_id = str(row.get("message_id") or "").strip()
        # Folder identity takes precedence over a derived direction label.
        if ("SENT" in folder or str(row.get("direction") or "").upper() == "OUTBOUND") and message_id and sender.endswith("@novogene.com"):
            outgoing[message_id] = (sender, set(re.findall(r"[\w.+-]+@[\w.-]+", recipient)))
    links = set()
    for row in rows:
        sender = str(row.get("from_email") or "").strip().lower()
        if not sender or sender.endswith("@novogene.com"):
            continue
        to = str(row.get("recipient_to") or "").lower()
        refs = pattern.findall(str(row.get("in_reply_to") or "") + " " + str(row.get("references") or ""))
        for ref in refs:
            evidence = outgoing.get(ref)
            if evidence and sender in evidence[1] and evidence[0] in to:
                links.add((ref, str(row.get("message_id") or "")))
    incoming_ids = {mid for _, mid in links if mid}
    matching_rows = [r for r in rows if str(r.get("message_id") or "") in incoming_ids
                     and str(r.get("from_email") or "").lower().endswith("@novogene.com") is False]
    return {
        "outgoing_ids": len(outgoing),
        "strict_reply_links": len(links),
        "linked_message_ids": sorted(incoming_ids),
        "linked_incoming_keys": sorted({str(r.get("ingest_key") or "") for r in matching_rows if r.get("ingest_key")}),
        "duplicate_incoming_rows": max(0, len(matching_rows) - len(incoming_ids)),
        "review_required": len(incoming_ids),
    }


def followup_after_verified_reply(rows, linked_message_ids):
    """Read-only correspondent/time check; not a completed-thread decision."""
    from datetime import datetime
    linked = set(linked_message_ids)
    replies, outgoing = {}, {}
    for row in rows:
        mid = str(row.get("message_id") or "").strip()
        sender = str(row.get("from_email") or "").strip().lower()
        recipient = str(row.get("recipient_to") or "").strip().lower()
        try:
            when = datetime.fromisoformat(str(row.get("received_at") or "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if when.tzinfo is None:
            continue
        if mid in linked and sender and not sender.endswith("@novogene.com"):
            replies[mid] = (sender, when)
        if sender.endswith("@novogene.com") and ("SENT" in str(row.get("folder") or "").upper()
             or str(row.get("direction") or "").upper() == "OUTBOUND"):
            outgoing[mid] = (recipient, when)
    result = {"verified_replies": len(replies), "later_outbound_confirmed": 0,
              "later_outbound_not_found": 0}
    for customer, reply_at in replies.values():
        answered = any(customer in recipient and when > reply_at for recipient, when in outgoing.values())
        result["later_outbound_confirmed" if answered else "later_outbound_not_found"] += 1
    return result



def update_followup_dashboard(api, rows, evidence, triage):
    """Update verified replies by UID, preserving dashboard manual decisions (column J)."""
    from datetime import datetime
    from nba_refresh_pool import MAIL_BOOK
    tab = "NBA Verified Reply Followup"
    current = api.values().get(spreadsheetId=MAIL_BOOK, range=f"'{tab}'!A2:K500").execute().get("values", [])
    index = {str(r[0]).strip().lower(): i + 2 for i, r in enumerate(current) if r and str(r[0]).strip()}
    outgoing = []
    for r in rows:
        sender = str(r.get("from_email") or "").strip().lower()
        recipient = str(r.get("recipient_to") or "").strip().lower()
        if not sender.endswith("@novogene.com"):
            continue
        if "SENT" not in str(r.get("folder") or "").upper() and str(r.get("direction") or "").upper() != "OUTBOUND":
            continue
        try:
            timestamp = datetime.fromisoformat(str(r.get("received_at") or "").replace("Z", "+00:00"))
            if timestamp.tzinfo:
                outgoing.append((recipient, timestamp))
        except (ValueError, TypeError):
            pass
    verified = set(evidence["linked_message_ids"])
    dedup = {}
    for r in rows:
        mid = str(r.get("message_id") or "")
        key = str(r.get("ingest_key") or "")
        if mid not in verified or not key.upper().startswith("INBOX|"):
            continue
        uid = "inbox:" + key.rsplit("|", 1)[-1]
        if uid not in triage or mid in dedup:
            continue
        try:
            reply_at = datetime.fromisoformat(str(r.get("received_at") or "").replace("Z", "+00:00"))
            if not reply_at.tzinfo:
                continue
        except (ValueError, TypeError):
            continue
        dedup[mid] = (uid, str(r.get("from_email") or "").strip().lower(), reply_at, triage[uid])
    updates = []
    from datetime import timezone, timedelta
    kst = timezone(timedelta(hours=9))
    for uid, customer, reply_at, triage_row in dedup.values():
        later = [dt for recipient, dt in outgoing if customer in recipient and dt > reply_at]
        prior = [dt for recipient, dt in outgoing if customer in recipient and dt <= reply_at]
        status = "LATER_OUTBOUND_CONFIRMED" if later else "LATER_OUTBOUND_NOT_FOUND"
        stamp = lambda dt: dt.astimezone(kst).strftime("%Y-%m-%d %H:%M:%S") if dt else ""
        row = [uid, customer, str(triage_row.get("Subject / Thread") or ""), stamp(reply_at),
               stamp(max(prior) if prior else None), status, "HEADER_EXACT",
               str(triage_row.get("Effective Queue") or ""), "CSS Git Ingest / Message-ID"]
        target = index.get(uid)
        if target is None:
            target = max([1] + list(index.values())) + 1
            index[uid] = target
        updates.append({"range": f"'{tab}'!A{target}:I{target}", "values": [row]})
        updates.append({"range": f"'{tab}'!K{target}", "values": [[datetime.now(kst).date().isoformat()]]})
    if updates:
        api.values().batchUpdate(spreadsheetId=MAIL_BOOK, body={"valueInputOption": "RAW", "data": updates}).execute()
        verified = api.values().get(spreadsheetId=MAIL_BOOK, range=f"\u0027{tab}\u0027!A2:K500").execute().get("values", [])
        by_uid = {str(r[0]).strip().lower(): r for r in verified if r and str(r[0]).strip()}
        for item in updates:
            if ":I" not in item["range"]:
                continue
            values = item["values"][0]
            actual = by_uid.get(values[0].lower(), [])
            if len(actual) < 9 or actual[:9] != values:
                raise ValueError("NBA reply dashboard write verification failed: " + values[0])
    print("NBA_REPLY_DASHBOARD_UPDATED", len(dedup), "READBACK_VERIFIED=true MANUAL_DECISIONS_UNCHANGED=true")



def main():
    from nba_google_auth import auth
    from nba_refresh_pool import fetch, MAIL_BOOK
    rows = fetch(auth(), MAIL_BOOK, "BI Unanswered Triage", "U20000")
    print("NBA_MAIL_EVIDENCE_AUDIT", summarize(rows))
    stage = fetch(auth(), MAIL_BOOK, "CSS Git Ingest", "R12000")
    evidence = exact_header_reply_links(stage)
    triage_by_uid = {str(r.get("Thread UID") or "").strip().lower(): r for r in rows}
    linked_uids = sorted({("inbox:" + key.rsplit("|", 1)[-1]).lower()
                         for key in evidence["linked_incoming_keys"]
                         if key.upper().startswith("INBOX|")})
    matched = [uid for uid in linked_uids if uid in triage_by_uid]
    print("NBA_EXACT_HEADER_REPLY_AUDIT", evidence)
    print("NBA_REPLY_FOLLOWUP_AUDIT", followup_after_verified_reply(stage, evidence["linked_message_ids"]))
    import os
    if os.getenv("NBA_REPLY_DASHBOARD_WRITE", "false").lower() == "true":
        update_followup_dashboard(auth(), stage, evidence, triage_by_uid)
    print("NBA_REPLY_TRIAGE_JOIN", {
        "unique_linked_uids": len(linked_uids),
        "triage_matched_uids": len(matched),
        "triage_missing_uids": sorted(set(linked_uids) - set(matched)),
        "matched_queue_states": {uid: str(triage_by_uid[uid].get("Effective Queue") or "")
                                 for uid in matched},
    })


if __name__ == "__main__":
    main()
