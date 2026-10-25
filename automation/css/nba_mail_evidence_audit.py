"""Read-only audit of QQ unanswered evidence quality for NBA.

Do not infer replies from customer names, matching subjects, or review notes.
Report confirmed replies separately from ambiguous triage evidence.
"""
from collections import Counter
from today_action_v2 import mail_rows

CONFIRMED = {
    "SENT_CONFIRMED", "REPLIED", "ANSWERED", "REPLY_SENT", "DONE",
    "PC_REPLIED", "TS_REPLIED", "DELEGATE_REPLIED",
}
CONFIRMED_ACTION = CONFIRMED | {"COMPLETED", "CLOSED"}


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
        if reply in CONFIRMED or reviewer in CONFIRMED_ACTION:
            counts["explicit_reply_evidence"] += 1
        elif reply and reply not in {"NONE", "UNKNOWN"}:
            counts["ambiguous_reply_evidence"] += 1
        if age > 30:
            counts["historical_over_30d"] += 1
    counts["nba_actionable"] = len(mail_rows(rows))
    return dict(counts)


def main():
    from nba_google_auth import auth
    from nba_refresh_pool import fetch, MAIL_BOOK
    rows = fetch(auth(), MAIL_BOOK, "BI Unanswered Triage", "U20000")
    print("NBA_MAIL_EVIDENCE_AUDIT", summarize(rows))


if __name__ == "__main__":
    main()
