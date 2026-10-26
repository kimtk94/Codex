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
    return {"outgoing_ids": len(outgoing), "strict_reply_links": len(links), "linked_message_ids": sorted({reply for _, reply in links if reply}), "linked_incoming_keys": sorted({str(r.get("ingest_key") or "") for r in rows if str(r.get("message_id") or "") in {mid for _, mid in links} and str(r.get("ingest_key") or "")})}

def main():
    from nba_google_auth import auth
    from nba_refresh_pool import fetch, MAIL_BOOK
    rows = fetch(auth(), MAIL_BOOK, "BI Unanswered Triage", "U20000")
    print("NBA_MAIL_EVIDENCE_AUDIT", summarize(rows))
    stage = fetch(auth(), MAIL_BOOK, "CSS Git Ingest", "R12000")
    print("NBA_EXACT_HEADER_REPLY_AUDIT", exact_header_reply_links(stage))


if __name__ == "__main__":
    main()
